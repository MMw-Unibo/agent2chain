from __future__ import annotations

from urllib.parse import quote

from utils.tool_utils import (
	compute_percentage_change_from_series,
	extract_chain_value,
	extract_token_value_from_chain_series,
	fetch_json_url,
	normalize_compact_key,
	normalize_text_key,
	pick_best_named_entry,
	resolve_chain_display_name,
	resolve_protocol_slug,
	slugify_text,
)


LLAMA_BASE_URL = "https://api.llama.fi"


async def getTVL(
	protocol: str = "",
	chain: str = "",
	tokenSymbol: str = "",
	changeWindow: str = "1d",
) -> dict:
	"""Get TVL data via DefiLlama for protocol or chain, with optional token/chain filtering and change rates."""
	try:
		if not str(protocol or "").strip() and not str(chain or "").strip():
			return {
				"error": "Provide at least one of: protocol or chain",
				"source": "defillama",
			}

		resolved_chain = resolve_chain_display_name(chain)
		window = normalize_text_key(changeWindow) or "1d"

		if str(protocol or "").strip():
			protocols = fetch_json_url(f"{LLAMA_BASE_URL}/protocols", timeout=12)
			if not isinstance(protocols, list):
				return {
					"error": "Unexpected response from DefiLlama /protocols",
					"source": "defillama",
				}

			query = resolve_protocol_slug(protocol)
			entry = pick_best_named_entry(query, protocols)
			if not entry:
				return {
					"error": f"Protocol not found on DefiLlama: {protocol}",
					"source": "defillama",
				}

			name = str(entry.get("name") or "")
			symbol = str(entry.get("symbol") or "")
			slug = str(entry.get("slug") or slugify_text(name))
			current_tvl = entry.get("tvl")
			if not isinstance(current_tvl, (int, float)):
				current_tvl = None

			chain_tvl = None
			if resolved_chain:
				chain_tvl = extract_chain_value(entry, resolved_chain)

			change_rate = None
			if window == "7d":
				change_rate = entry.get("change_7d")
			else:
				change_rate = entry.get("change_1d")

			token_tvl = None
			if str(tokenSymbol or "").strip():
				detail = fetch_json_url(
					f"{LLAMA_BASE_URL}/protocol/{quote(slug)}",
					timeout=12,
				)
				token_tvl = extract_token_value_from_chain_series(detail, tokenSymbol, resolved_chain)

			return {
				"protocol": name,
				"protocolSymbol": symbol,
				"protocolSlug": slug,
				"tvlUsd": current_tvl,
				"chain": resolved_chain or None,
				"chainTvlUsd": chain_tvl,
				"tokenSymbol": tokenSymbol.upper() if tokenSymbol else None,
				"tokenTvlUsd": token_tvl,
				"changeWindow": "7d" if window == "7d" else "1d",
				"changeRatePct": float(change_rate) if isinstance(change_rate, (int, float)) else None,
				"source": "defillama",
			}

		# Chain-only flow
		chains = fetch_json_url(f"{LLAMA_BASE_URL}/v2/chains", timeout=12)
		if not isinstance(chains, list):
			return {
				"error": "Unexpected response from DefiLlama /v2/chains",
				"source": "defillama",
			}

		target_norm = normalize_compact_key(resolved_chain)
		chain_entry = None
		for item in chains:
			name = str(item.get("name") or "")
			if normalize_compact_key(name) == target_norm:
				chain_entry = item
				break

		if not chain_entry:
			return {
				"error": f"Chain not found on DefiLlama: {chain}",
				"source": "defillama",
			}

		chain_name = str(chain_entry.get("name") or resolved_chain)
		chain_tvl = chain_entry.get("tvl")

		historical = fetch_json_url(
			f"{LLAMA_BASE_URL}/v2/historicalChainTvl/{quote(chain_name)}",
			timeout=12,
		)
		if not isinstance(historical, list):
			historical = []

		window_days = 7 if window == "7d" else 1
		change_rate = compute_percentage_change_from_series(historical, window_days, value_key="tvl")

		return {
			"chain": chain_name,
			"tvlUsd": float(chain_tvl) if isinstance(chain_tvl, (int, float)) else None,
			"changeWindow": "7d" if window == "7d" else "1d",
			"changeRatePct": change_rate,
			"source": "defillama",
		}
	except Exception as error:
		return {
			"error": f"getTVL error: {error}",
			"source": "defillama",
		}