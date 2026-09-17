import sys
from pathlib import Path

from eth_utils import to_checksum_address

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
	sys.path.append(str(SRC_ROOT))

from defiReadUtils import (
	derive_spender_from_route,
	encode_function_call,
	eth_call_strict,
	format_units,
	resolve_chain_data,
	resolve_token_config,
)
from utils.tool_utils import is_valid_evm_address


async def getTokenAllowance(
	networkName: str,
	tokenSymbol: str,
	ownerAddress: str,
	spenderAddress: str = "",
	protocolName: str = "",
	operation: str = "",
	requestedAmount: str = "",
) -> dict:
	"""Read ERC20 allowance for owner->spender, with optional route-based spender derivation."""
	try:
		if not is_valid_evm_address(ownerAddress):
			return {"error": "getTokenAllowance error: Invalid ownerAddress", "source": "defi"}

		token_cfg = resolve_token_config(networkName, tokenSymbol, protocolName or None)
		if token_cfg.get("isNative"):
			return {
				"error": "getTokenAllowance error: Native tokens do not have ERC20 allowance",
				"source": "defi",
			}

		token_address = token_cfg.get("address")
		if not is_valid_evm_address(token_address):
			return {
				"error": "getTokenAllowance error: Token address missing or invalid in configuration",
				"source": "defi",
			}

		resolved_spender = spenderAddress.strip()
		if not resolved_spender and protocolName and operation:
			resolved_spender = derive_spender_from_route(
				network_name=networkName,
				protocol_name=protocolName,
				operation=operation,
				token_symbol=tokenSymbol,
			) or ""
		if not is_valid_evm_address(resolved_spender):
			return {
				"error": (
					"getTokenAllowance error: spenderAddress is required or must be derivable from "
					"protocolName+operation route"
				),
				"source": "defi",
			}

		chain_key, chain_data = resolve_chain_data(networkName)
		rpc_urls = chain_data.get("rpcUrls") or []
		data_hex = encode_function_call("allowance(address,address)", [ownerAddress, resolved_spender])
		raw = eth_call_strict(rpc_urls, str(token_address), data_hex)
		allowance_units = int(raw, 16)
		decimals = int(token_cfg.get("decimals") or 18)

		result = {
			"network": chain_key,
			"token": tokenSymbol.upper(),
			"tokenAddress": to_checksum_address(str(token_address)),
			"owner": to_checksum_address(ownerAddress),
			"spender": to_checksum_address(resolved_spender),
			"decimals": decimals,
			"allowanceUnits": str(allowance_units),
			"allowance": format_units(allowance_units, decimals),
			"source": "defi",
		}

		if requestedAmount and requestedAmount.strip():
			from defiReadUtils import amount_to_units
			requested_units = amount_to_units(requestedAmount, decimals)
			result["requestedAmount"] = requestedAmount
			result["requestedAmountUnits"] = str(requested_units)
			result["isEnough"] = allowance_units >= requested_units

		return result
	except Exception as error:
		return {"error": f"getTokenAllowance error: {error}", "source": "defi"}
