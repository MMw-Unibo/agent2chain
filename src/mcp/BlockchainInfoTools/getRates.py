from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from utils.tool_utils import normalize_text_key

BITCOMPARE_RATES_BASE = "https://api.bitcompare.net/api/v1/rates"
VALID_CATEGORIES = {"lending", "borrowing", "staking", "price"}

def _clamp_limit(limit: int, *, default: int = 100, max_value: int = 200) -> int:
    try:
        value = int(limit)
    except Exception:
        return default
    if value < 1:
        return 1
    if value > max_value:
        return max_value
    return value


def _fetch_bitcompare_json(url: str, timeout: int = 15) -> dict:
    headers = {
        "User-Agent": "BlockchainAgentADK/1.0",
        "Accept": "application/json",
    }

    api_key = os.getenv("BITCOMPARE_API_KEY", "").strip()
    if api_key:
        headers["X-API-Key"] = api_key

    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_chain_value(rate_row: dict[str, Any]) -> str:
    metadata = rate_row.get("metadata")
    if not isinstance(metadata, dict):
        return ""

    for key in ("chain", "network", "blockchain"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _extract_collateral_value(rate_row: dict[str, Any]) -> str:
    metadata = rate_row.get("metadata")
    if not isinstance(metadata, dict):
        return ""

    for key in ("collateral", "collateralSymbol", "collateralAsset"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _extract_rate_value(rate_row: dict[str, Any]) -> float | None:
    direct_rate = rate_row.get("rate")
    if isinstance(direct_rate, (int, float)):
        return float(direct_rate)

    metadata = rate_row.get("metadata")
    if not isinstance(metadata, dict):
        return None

    meta_rate = metadata.get("rate")
    if isinstance(meta_rate, (int, float)):
        return float(meta_rate)

    all_chains = metadata.get("allChains")
    if isinstance(all_chains, list):
        selected_chain = normalize_text_key(metadata.get("selectedChain"))
        chosen_rate: float | None = None
        for entry in all_chains:
            if not isinstance(entry, dict):
                continue
            entry_rate = entry.get("rate")
            if not isinstance(entry_rate, (int, float)):
                continue
            entry_chain = normalize_text_key(entry.get("chain"))
            if selected_chain and entry_chain == selected_chain:
                return float(entry_rate)
            if chosen_rate is None or float(entry_rate) < chosen_rate:
                chosen_rate = float(entry_rate)
        return chosen_rate

    return None


async def getRates(
    symbol: str = "",
    category: str = "",
    provider: str = "",
    chain: str = "",
    collateral: str = "",
    limit: int = 100,
    sort: str = "rate_desc",
) -> dict:
    """Get rates from Bitcompare (lending, borrowing, staking, price)."""
    try:
        symbol_filter = normalize_text_key(symbol).upper()
        category_filter = normalize_text_key(category)
        provider_filter = normalize_text_key(provider)
        chain_filter = normalize_text_key(chain)
        collateral_filter = normalize_text_key(collateral)
        sort_key = normalize_text_key(sort) or "rate_desc"

        if category_filter and category_filter not in VALID_CATEGORIES:
            return {
                "error": f"Invalid category '{category}'. Use one of: lending, borrowing, staking, price.",
                "source": "Bitcompare",
                "endpoint": BITCOMPARE_RATES_BASE,
            }

        query_params: dict[str, Any] = {
            "limit": _clamp_limit(limit),
        }
        if symbol_filter:
            query_params["symbol"] = symbol_filter
        if category_filter:
            query_params["category"] = category_filter
        if provider_filter:
            query_params["provider"] = provider_filter

        request_url = f"{BITCOMPARE_RATES_BASE}?{urlencode(query_params)}"
        payload = _fetch_bitcompare_json(request_url, timeout=20)

        data_node = payload.get("data") if isinstance(payload, dict) else None
        rates = data_node.get("rates") if isinstance(data_node, dict) else None
        if not isinstance(rates, list):
            return {
                "error": "Malformed response from Bitcompare rates endpoint",
                "source": "Bitcompare",
                "endpoint": request_url,
            }

        filtered: list[dict[str, Any]] = []
        for item in rates:
            if not isinstance(item, dict):
                continue

            item_symbol = str(item.get("symbol") or "")
            item_category = str(item.get("category") or "")
            item_provider = str(item.get("provider") or "")
            item_chain = _extract_chain_value(item)
            item_collateral = _extract_collateral_value(item)

            if chain_filter and normalize_text_key(item_chain) != chain_filter:
                continue
            if collateral_filter and normalize_text_key(item_collateral) != collateral_filter:
                continue

            rate_number = _extract_rate_value(item)

            filtered.append(
                {
                    "provider": item_provider,
                    "symbol": item_symbol,
                    "category": item_category,
                    "rate": rate_number,
                    "lastUpdated": item.get("lastUpdated"),
                    "coinId": item.get("coinId"),
                    "providerSymbol": item.get("providerSymbol"),
                    "chain": item_chain or None,
                    "collateral": item_collateral or None,
                    "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else None,
                }
            )

        valid = [row for row in filtered if row.get("rate") is not None]
        invalid = [row for row in filtered if row.get("rate") is None]

        if sort_key == "rate_asc":
            valid.sort(key=lambda row: float(row.get("rate") or 0))
        else:
            valid.sort(key=lambda row: float(row.get("rate") or 0), reverse=True)

        ordered = valid + invalid
        bounded_limit = _clamp_limit(limit)
        results = ordered[:bounded_limit]

        return {
            "count": len(results),
            "totalMatched": len(ordered),
            "filters": {
                "symbol": symbol_filter or None,
                "category": category_filter or None,
                "provider": provider_filter or None,
                "chain": chain_filter or None,
                "collateral": collateral_filter or None,
                "sort": "rate_asc" if sort_key == "rate_asc" else "rate_desc",
            },
            "rates": results,
            "source": "Bitcompare",
            "endpoint": request_url,
            "notes": "Rates category supports lending, borrowing, staking, and price.",
        }
    except Exception as error:
        return {
            "error": f"getRates error: {error}",
            "source": "Bitcompare",
            "endpoint": BITCOMPARE_RATES_BASE,
        }
