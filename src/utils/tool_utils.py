import json
import os
import re
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from utils.supported_chains import resolve_chain


DEFAULT_USER_AGENT = "BlockchainAgentADK/1.0"
ETHERSCAN_V2_BASE = "https://api.etherscan.io/v2/api"
EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


def fetch_json_url(url: str, timeout: int = 12) -> dict:
    request = Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json",
        },
        method="GET",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json_url(url: str, payload: dict, timeout: int = 12) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def rpc_call(rpc_url: str, method: str, params: list, timeout: int = 12):
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        }
    ).encode("utf-8")

    request = Request(
        rpc_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        },
        method="POST",
    )

    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("result")


def rpc_call_strict(rpc_url: str, method: str, params: list, timeout: int = 12):
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        }
    ).encode("utf-8")

    request = Request(
        rpc_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        },
        method="POST",
    )

    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if "error" in payload:
        raise ValueError(payload["error"].get("message", f"RPC error calling {method}"))
    return payload.get("result")


def rpc_call_with_fallback(rpc_urls: list[str], method: str, params: list, timeout: int = 12):
    last_error = None
    for rpc_url in rpc_urls:
        try:
            result = rpc_call(rpc_url, method, params, timeout=timeout)
            return result, None
        except Exception as rpc_error:
            last_error = rpc_error

    return None, last_error


def rpc_call_with_fallback_strict(rpc_urls: list[str], method: str, params: list, timeout: int = 12):
    last_error = None
    for rpc_url in rpc_urls:
        try:
            result = rpc_call_strict(rpc_url, method, params, timeout=timeout)
            return result, None
        except Exception as rpc_error:
            last_error = rpc_error

    return None, last_error


def estimate_fee_hex(rpc_urls: list[str], tx_object: dict, timeout: int = 8) -> tuple[str | None, str | None, str | None]:
    for rpc_url in rpc_urls:
        try:
            gas_estimate_hex = rpc_call_strict(rpc_url, "eth_estimateGas", [tx_object], timeout=timeout)
            gas_price_hex = rpc_call_strict(rpc_url, "eth_gasPrice", [], timeout=timeout)
            if not gas_estimate_hex or not gas_price_hex:
                continue

            total_fee_wei = int(gas_estimate_hex, 16) * int(gas_price_hex, 16)
            return gas_estimate_hex, gas_price_hex, hex(total_fee_wei)
        except Exception:
            continue

    return None, None, None


def fetch_etherscan_v2(chain_id: int, params: dict) -> dict:
    query = {
        "chainid": str(chain_id),
        **params,
    }
    api_key = os.getenv("ETHERSCAN_API_KEY")
    if api_key:
        query["apikey"] = api_key

    url = f"{ETHERSCAN_V2_BASE}?{urlencode(query)}"
    return fetch_json_url(url, timeout=12)


def is_valid_evm_address(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    return bool(EVM_ADDRESS_RE.match(value.strip()))


def parse_decimal_amount(raw_amount: str | int | float, *, allow_zero: bool = False) -> Decimal:
    amount = Decimal(str(raw_amount).strip())
    if allow_zero:
        if amount < 0:
            raise ValueError("Amount must be non-negative")
    else:
        if amount <= 0:
            raise ValueError("Amount must be positive")
    return amount


def decimal_to_wei_hex(amount: Decimal, *, allow_zero: bool = True) -> str:
    quantized = amount * Decimal("1000000000000000000")
    if quantized != quantized.to_integral_value():
        raise ValueError("Amount supports at most 18 decimal places")

    wei_int = int(quantized)
    if allow_zero:
        if wei_int < 0:
            raise ValueError("Invalid amount")
    else:
        if wei_int <= 0:
            raise ValueError("Invalid amount")

    return hex(wei_int)


def eth_to_wei_hex(value_eth: str | None, *, allow_zero: bool = True) -> str:
    if value_eth is None or str(value_eth).strip() == "":
        return "0x0"
    amount = parse_decimal_amount(str(value_eth), allow_zero=allow_zero)
    return decimal_to_wei_hex(amount, allow_zero=allow_zero)


def sanitize_name(name: str | None, *, default: str = "Contract", max_length: int = 60) -> str:
    if not name:
        return default
    safe = "".join(ch for ch in str(name) if ch.isalnum() or ch in "_-")
    return safe[:max_length] or default


def contracts_registry_path(from_file: str | Path) -> Path:
    return Path(from_file).resolve().parents[3] / ".data" / "contracts.storage.json"


def ensure_json_list_file(file_path: Path) -> Path:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if not file_path.exists():
        file_path.write_text("[]", encoding="utf-8")
    return file_path


def load_json_list_file(file_path: Path) -> list[dict]:
    path = ensure_json_list_file(file_path)
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        path.write_text("[]", encoding="utf-8")
        return []
    except Exception:
        path.write_text("[]", encoding="utf-8")
        return []


def load_contract_registry(from_file: str | Path) -> list[dict]:
    return load_json_list_file(contracts_registry_path(from_file))


def filter_contract_records(
    records: list[dict],
    *,
    user_address: str = "",
    network_name: str = "",
    contract_address: str = "",
    contract_name: str = "",
) -> list[dict]:
    filtered = list(records)

    if user_address:
        ua = user_address.strip().lower()
        filtered = [r for r in filtered if str(r.get("userAddress", "")).strip().lower() == ua]

    if network_name:
        nn = network_name.strip().lower()
        filtered = [r for r in filtered if str(r.get("networkName", "")).strip().lower() == nn]

    if contract_address:
        ca = contract_address.strip().lower()
        filtered = [r for r in filtered if str(r.get("contractAddress", "")).strip().lower() == ca]

    if contract_name:
        cn = contract_name.strip().lower()
        filtered = [r for r in filtered if str(r.get("contractName", "")).strip().lower() == cn]

    return filtered


CHAIN_DISPLAY_NAME_BY_KEY = {
    "ethereum-mainnet": "Ethereum",
    "arbitrum-one": "Arbitrum",
    "avalanche-c-chain": "Avalanche",
    "base-mainnet": "Base",
    "polygon-mainnet": "Polygon",
    "optimism-mainnet": "OP Mainnet",
    "bsc-mainnet": "BSC",
}

PROTOCOL_SLUG_ALIASES = {
    "aave": "aave-v3",
    "aave v3": "aave-v3",
    "aave-v3": "aave-v3",
    "compound": "compound-v3",
    "compound v3": "compound-v3",
    "compound-v3": "compound-v3",
    "lido": "lido",
    "venus": "venus-core-pool",
    "venus core pool": "venus-core-pool",
    "spark": "spark",
    "yldr": "yldr",
    "curve": "curve-lending",
    "curve lending": "curve-lending",
}

TOKEN_SYMBOL_GROUP_ALIASES = {
    "btc": {"BTC", "WBTC", "TBTC", "CBBTC", "FBTC"},
    "eth": {"ETH", "WETH", "STETH", "RETH", "WEETH", "EZETH"},
}


def normalize_text_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def normalize_compact_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def slugify_text(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def resolve_chain_display_name(chain: str | None) -> str:
    raw_input = str(chain or "").strip()
    if not raw_input:
        return ""

    chain_key, _ = resolve_chain(raw_input)
    if chain_key:
        return CHAIN_DISPLAY_NAME_BY_KEY.get(chain_key, raw_input)

    return raw_input


def resolve_protocol_slug(protocol: str | None) -> str:
    raw = normalize_text_key(protocol)
    if not raw:
        return ""

    from utils.supported_tokens import resolve_protocol_id

    normalized_supported = resolve_protocol_id(raw)
    return PROTOCOL_SLUG_ALIASES.get(raw, normalized_supported)


def pick_best_named_entry(query_text: str, entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    query = normalize_text_key(query_text)
    if not query:
        return None

    candidates: list[tuple[int, dict[str, Any]]] = []
    for item in entries:
        name = str(item.get("name") or "")
        symbol = str(item.get("symbol") or "")
        slug = str(item.get("slug") or slugify_text(name))

        name_norm = normalize_text_key(name)
        symbol_norm = normalize_text_key(symbol)
        slug_norm = normalize_text_key(slug)

        score = -1
        if query == slug_norm:
            score = 100
        elif query == name_norm:
            score = 95
        elif query == symbol_norm:
            score = 90
        elif query in name_norm:
            score = 70
        elif query in slug_norm:
            score = 65
        elif name_norm in query and name_norm:
            score = 60

        if score >= 0:
            candidates.append((score, item))

    if not candidates:
        return None

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[0][1]


def extract_chain_value(entry: dict[str, Any], chain_name: str) -> float | None:
    chain_tvls = entry.get("chainTvls") or {}
    if not isinstance(chain_tvls, dict):
        return None

    target_norm = normalize_compact_key(chain_name)
    for key, value in chain_tvls.items():
        if not isinstance(value, (int, float)):
            continue
        if normalize_compact_key(str(key).split("-")[0]) == target_norm:
            return float(value)
    return None


def _token_candidates(token_symbol: str) -> set[str]:
    base = normalize_compact_key(token_symbol).upper()
    if not base:
        return set()
    return {base, *(TOKEN_SYMBOL_GROUP_ALIASES.get(base.lower(), set()))}


def extract_token_value_from_chain_series(
    protocol_detail: dict[str, Any],
    token_symbol: str,
    chain_name: str = "",
) -> float:
    chains = protocol_detail.get("chainTvls") or {}
    if not isinstance(chains, dict):
        return 0.0

    token_names = _token_candidates(token_symbol)
    if not token_names:
        return 0.0

    target_chain_norm = normalize_compact_key(chain_name)
    total = 0.0

    for chain_key, chain_payload in chains.items():
        if not isinstance(chain_payload, dict):
            continue

        base_chain = str(chain_key).split("-")[0]
        if target_chain_norm and normalize_compact_key(base_chain) != target_chain_norm:
            continue

        tokens_series = chain_payload.get("tokens") or []
        if not isinstance(tokens_series, list) or not tokens_series:
            continue

        latest = tokens_series[-1]
        if not isinstance(latest, dict):
            continue
        latest_tokens = latest.get("tokens") or {}
        if not isinstance(latest_tokens, dict):
            continue

        for token_key, token_value in latest_tokens.items():
            if not isinstance(token_value, (int, float)):
                continue
            key_norm = normalize_compact_key(token_key).upper()
            if key_norm in token_names:
                total += float(token_value)

    return total


def compute_percentage_change_from_series(
    series: list[dict[str, Any]],
    days: int,
    value_key: str = "tvl",
) -> float | None:
    if not isinstance(series, list) or len(series) < days + 1:
        return None

    latest = series[-1]
    older = series[-(days + 1)]
    if not isinstance(latest, dict) or not isinstance(older, dict):
        return None

    latest_tvl = latest.get(value_key)
    older_tvl = older.get(value_key)
    if not isinstance(latest_tvl, (int, float)) or not isinstance(older_tvl, (int, float)):
        return None
    if older_tvl == 0:
        return None

    return ((float(latest_tvl) - float(older_tvl)) / float(older_tvl)) * 100.0


ASSET_ID_ALIASES = {
    "eth": "ethereum",
    "ether": "ethereum",
    "ethereum": "ethereum",
    "btc": "bitcoin",
    "xbt": "bitcoin",
    "bitcoin": "bitcoin",
    "bnb": "binancecoin",
    "binance": "binancecoin",
    "matic": "matic-network",
    "polygon": "matic-network",
    "pol": "polygon-ecosystem-token",
    "avax": "avalanche-2",
    "avalanche": "avalanche-2",
    "arb": "arbitrum",
    "arbitrum": "arbitrum",
    "op": "optimism",
    "optimism": "optimism",
    "link": "chainlink",
    "chainlink": "chainlink",
    "dai": "dai",
    "usdc": "usd-coin",
    "usd-coin": "usd-coin",
    "usdt": "tether",
    "tether": "tether",
}


def resolve_asset_id(raw_asset: str | None, *, default_asset: str = "ethereum") -> tuple[str, str]:
    if not raw_asset:
        return default_asset, default_asset

    normalized_input = normalize_text_key(raw_asset)
    return ASSET_ID_ALIASES.get(normalized_input, normalized_input), normalized_input


def parse_csv_values(raw_values: str | None, *, default_values: list[str] | None = None) -> list[str]:
    if not raw_values:
        return list(default_values or [])

    values = [normalize_text_key(item) for item in str(raw_values).split(",")]
    return [item for item in values if item]


LENDING_RATE_CHAIN_FILTER_BY_CHAIN_KEY = {
    "ethereum-mainnet": "ethereum",
    "arbitrum-one": "arbitrum",
    "avalanche-c-chain": "avalanche",
    "base-mainnet": "base",
    "polygon-mainnet": "polygon",
    "optimism-mainnet": "optimism",
    "bsc-mainnet": "bsc",
}

PLATFORM_FILTER_ALIASES = {
    "aave": "aave",
    "aave v3": "aave",
    "aave-v3": "aave",
    "compound": "compound",
    "compound v3": "compound",
    "compound-v3": "compound",
    "venus": "venus",
    "venus core pool": "venus",
    "venus-core-pool": "venus",
    "spark": "spark",
    "morpho": "morpho",
    "euler": "euler",
    "fluid": "fluid",
    "lista": "lista",
}


def resolve_lending_rate_chain_filter(chain: str | None) -> str:
    raw_input = str(chain or "").strip()
    if not raw_input:
        return ""

    chain_key, _ = resolve_chain(raw_input)
    if chain_key:
        return LENDING_RATE_CHAIN_FILTER_BY_CHAIN_KEY.get(chain_key, normalize_text_key(raw_input))

    return normalize_text_key(raw_input)


def resolve_platform_filter(platform: str | None) -> str:
    raw = normalize_text_key(platform)
    if not raw:
        return ""
    return PLATFORM_FILTER_ALIASES.get(raw, raw)


def parse_percentage_value(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.replace("%", "").replace(",", "").strip()
        if not normalized:
            return None
        try:
            return float(normalized)
        except Exception:
            return None
    return None