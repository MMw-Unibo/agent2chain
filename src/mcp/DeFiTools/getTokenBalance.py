import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
	sys.path.append(str(SRC_ROOT))

from defiReadUtils import (
	encode_function_call,
	eth_call_strict,
	format_units,
	resolve_chain_data,
	resolve_token_config,
)
from utils.tool_utils import is_valid_evm_address, rpc_call_with_fallback_strict


async def getTokenBalance(
	networkName: str,
	tokenSymbol: str,
	userAddress: str,
	protocolName: str = "",
) -> dict:
	"""Read token balance for an address on a supported network/protocol."""
	try:
		if not is_valid_evm_address(userAddress):
			return {"error": "getTokenBalance error: Invalid userAddress", "source": "defi"}

		token_cfg = resolve_token_config(networkName, tokenSymbol, protocolName or None)
		chain_key, chain_data = resolve_chain_data(networkName)
		rpc_urls = chain_data.get("rpcUrls") or []

		decimals = int(token_cfg.get("decimals") or 18)
		if token_cfg.get("isNative"):
			raw_balance, error = rpc_call_with_fallback_strict(
				rpc_urls,
				"eth_getBalance",
				[userAddress, "latest"],
				timeout=12,
			)
			if not isinstance(raw_balance, str):
				return {"error": f"getTokenBalance error: {error}", "source": "defi"}
			balance_units = int(raw_balance, 16)
			return {
				"network": chain_key,
				"token": tokenSymbol.upper(),
				"isNative": True,
				"address": None,
				"decimals": decimals,
				"owner": userAddress,
				"balanceUnits": str(balance_units),
				"balance": format_units(balance_units, decimals),
				"source": "defi",
			}

		token_address = token_cfg.get("address")
		if not is_valid_evm_address(token_address):
			return {
				"error": "getTokenBalance error: Token address missing or invalid in configuration",
				"source": "defi",
			}

		data_hex = encode_function_call("balanceOf(address)", [userAddress])
		raw = eth_call_strict(rpc_urls, str(token_address), data_hex)
		balance_units = int(raw, 16)
		return {
			"network": chain_key,
			"token": tokenSymbol.upper(),
			"isNative": False,
			"address": token_address,
			"decimals": decimals,
			"owner": userAddress,
			"balanceUnits": str(balance_units),
			"balance": format_units(balance_units, decimals),
			"source": "defi",
		}
	except Exception as error:
		return {"error": f"getTokenBalance error: {error}", "source": "defi"}
