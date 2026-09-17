import json
import sys
from pathlib import Path

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import keccak, to_checksum_address

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
	sys.path.append(str(SRC_ROOT))

from utils.tool_utils import (
	estimate_fee_hex,
	eth_to_wei_hex,
	filter_contract_records,
	is_valid_evm_address,
	load_contract_registry,
	rpc_call_with_fallback_strict,
	resolve_chain,
)


def _parse_function_args(raw) -> list:
	if raw is None or raw == "":
		return []
	if isinstance(raw, list):
		return raw
	if isinstance(raw, (int, float, bool)):
		return [raw]
	if isinstance(raw, str):
		candidate = raw.strip()
		if not candidate:
			return []
		try:
			parsed = json.loads(candidate)
		except json.JSONDecodeError:
			return [raw]

		if isinstance(parsed, list):
			return parsed
		if isinstance(parsed, (dict, int, float, bool, str)):
			return [parsed]
		raise ValueError("functionArgs must be a JSON array or scalar value")
	raise ValueError("functionArgs must be a list, scalar, or JSON string")


def _normalize_int(value):
	if isinstance(value, bool):
		raise ValueError("Boolean value is not valid for integer types")
	if isinstance(value, int):
		return value
	if isinstance(value, str):
		raw = value.strip().lower()
		if raw.startswith("0x"):
			return int(raw, 16)
		return int(raw)
	raise ValueError(f"Cannot parse integer value: {value}")


def _normalize_bool(value):
	if isinstance(value, bool):
		return value
	if isinstance(value, str):
		raw = value.strip().lower()
		if raw in {"true", "1", "yes"}:
			return True
		if raw in {"false", "0", "no"}:
			return False
	raise ValueError(f"Cannot parse bool value: {value}")


def _normalize_bytes(value):
	if isinstance(value, (bytes, bytearray)):
		return bytes(value)
	if isinstance(value, str):
		raw = value.strip()
		if raw.startswith("0x"):
			raw = raw[2:]
		if len(raw) % 2 != 0:
			raw = f"0{raw}"
		return bytes.fromhex(raw)
	raise ValueError(f"Cannot parse bytes value: {value}")


def _normalize_type_value(abi_type: str, value):
	if abi_type.endswith("]"):
		if not isinstance(value, list):
			raise ValueError(f"Type {abi_type} requires an array")
		base_type = abi_type[: abi_type.rfind("[")]
		return [_normalize_type_value(base_type, item) for item in value]

	if abi_type == "address":
		if not is_valid_evm_address(value):
			raise ValueError(f"Invalid address: {value}")
		return to_checksum_address(value)

	if abi_type == "bool":
		return _normalize_bool(value)

	if abi_type.startswith("uint") or abi_type.startswith("int"):
		return _normalize_int(value)

	if abi_type.startswith("bytes"):
		return _normalize_bytes(value)

	if abi_type == "string":
		return str(value)

	return value


def _function_signature(fragment: dict) -> str:
	name = str(fragment.get("name") or "").strip()
	input_types = [str(inp.get("type") or "") for inp in (fragment.get("inputs") or [])]
	return f"{name}({','.join(input_types)})"


def _find_function_fragment(abi: list[dict], function_name: str, arg_count: int) -> dict:
	functions = [
		item
		for item in abi
		if item.get("type") == "function" and str(item.get("name") or "") == function_name
	]
	if not functions:
		raise ValueError(f"Function '{function_name}' not found in contract ABI")

	matching = [f for f in functions if len(f.get("inputs") or []) == arg_count]
	if len(matching) == 1:
		return matching[0]
	if len(matching) > 1:
		signatures = ", ".join(_function_signature(f) for f in matching)
		raise ValueError(
			"Function overload is ambiguous for provided argument count. "
			f"Matching signatures: {signatures}"
		)

	available = ", ".join(_function_signature(f) for f in functions)
	raise ValueError(
		f"Function '{function_name}' expects a different number of arguments. "
		f"Available signatures: {available}"
	)


def _decode_read_outputs(raw_result: str, output_types: list[str]) -> list:
	if not output_types:
		return []
	raw_bytes = bytes.fromhex(raw_result[2:] if raw_result.startswith("0x") else raw_result)
	decoded = abi_decode(output_types, raw_bytes)

	serializable: list = []
	for item in decoded:
		if isinstance(item, bytes):
			serializable.append(f"0x{item.hex()}")
		elif isinstance(item, tuple):
			serializable.append(list(item))
		else:
			serializable.append(item)
	return serializable


async def interactWithContract(
	networkName: str,
	functionName: str,
	contractAddress: str = "",
	contractName: str = "",
	userAddress: str = "",
	functionArgs: str = "",
	valueEth: str = "",
) -> dict:
	"""Prepare or execute interaction with a deployed contract from local registry."""
	try:
		if not functionName or not str(functionName).strip():
			return {"error": "interactWithContract error: Missing functionName", "source": "metamask"}
		if not networkName or not str(networkName).strip():
			return {"error": "interactWithContract error: Missing networkName", "source": "metamask"}

		chain_key, chain_data = resolve_chain(networkName)
		if not chain_data:
			return {
				"error": f"interactWithContract error: Unknown network: {networkName}",
				"source": "metamask",
			}

		records = filter_contract_records(
			load_contract_registry(__file__),
			user_address=userAddress,
			network_name=networkName,
			contract_address=contractAddress,
			contract_name=contractName,
		)

		if not records:
			return {
				"message": "No contract matching the provided filters.",
				"source": "local-registry",
			}

		if len(records) > 1:
			preview = [
				f"{r.get('contractName') or '(Unnamed)'} @ {r.get('contractAddress')} [{r.get('networkName')}]"
				for r in records[:20]
			]
			return {
				"message": "More than one contract matches. Specify contractAddress.",
				"matches": len(records),
				"preview": preview,
				"source": "local-registry",
			}

		contract = records[0]
		resolved_address = str(contract.get("contractAddress") or "").strip()
		if not is_valid_evm_address(resolved_address):
			return {
				"error": "interactWithContract error: Selected contract has an invalid or missing address",
				"source": "local-registry",
			}

		abi = contract.get("abi") if isinstance(contract.get("abi"), list) else []
		if not abi:
			return {
				"error": "interactWithContract error: ABI not available for this contract",
				"source": "local-registry",
			}

		args = _parse_function_args(functionArgs)
		fragment = _find_function_fragment(abi, str(functionName).strip(), len(args))

		inputs = fragment.get("inputs") or []
		input_types = [str(inp.get("type") or "") for inp in inputs]
		normalized_args = [
			_normalize_type_value(input_types[index], args[index]) for index in range(len(input_types))
		]

		signature = _function_signature(fragment)
		selector = keccak(text=signature)[:4]
		encoded_args = abi_encode(input_types, normalized_args) if input_types else b""
		data_hex = f"0x{(selector + encoded_args).hex()}"

		mutability = str(fragment.get("stateMutability") or "nonpayable")
		is_read_only = mutability in {"view", "pure"}

		value_hex = eth_to_wei_hex(valueEth, allow_zero=True)
		if mutability != "payable" and value_hex != "0x0":
			return {
				"error": f"interactWithContract error: Function '{functionName}' is not payable; omit valueEth",
				"source": "metamask",
			}

		tx_template = {
			"to": to_checksum_address(resolved_address),
			"data": data_hex,
		}

		if value_hex != "0x0":
			tx_template["value"] = value_hex

		rpc_urls = chain_data.get("rpcUrls") or []
		if not rpc_urls:
			return {
				"error": f"interactWithContract error: No RPC URL configured for network {networkName}",
				"source": "metamask",
			}

		if is_read_only:
			raw_result, last_error = rpc_call_with_fallback_strict(
				rpc_urls,
				"eth_call",
				[tx_template, "latest"],
				timeout=10,
			)

			if not isinstance(raw_result, str):
				return {
					"error": f"interactWithContract error: Static call failed: {last_error}",
					"source": "metamask",
				}

			output_types = [str(out.get("type") or "") for out in (fragment.get("outputs") or [])]
			decoded = _decode_read_outputs(raw_result, output_types)

			return {
				"message": "Read-only function executed successfully.",
				"interaction": {
					"mode": "read",
					"contractName": contract.get("contractName") or "(Unnamed)",
					"contractAddress": to_checksum_address(resolved_address),
					"networkName": chain_key,
					"function": functionName,
					"signature": signature,
					"args": args,
					"outputs": decoded,
					"rawResult": raw_result,
				},
				"source": "metamask",
			}

		gas_estimate_hex = None
		gas_price_hex = None
		estimated_fee_wei_hex = None

		estimate_tx = dict(tx_template)
		if userAddress and is_valid_evm_address(userAddress):
			estimate_tx["from"] = to_checksum_address(userAddress)

		gas_estimate_hex, gas_price_hex, estimated_fee_wei_hex = estimate_fee_hex(
			rpc_urls,
			estimate_tx,
			timeout=10,
		)

		transaction_data = {
			"from": to_checksum_address(userAddress) if is_valid_evm_address(userAddress) else None,
			"to": to_checksum_address(resolved_address),
			"networkName": chain_key,
			"chainName": chain_key,
			"chainId": chain_data.get("chainId"),
			"chainIdHex": hex(int(chain_data["chainId"])),
			"symbol": chain_data.get("symbol"),
			"rpcUrls": rpc_urls,
			"data": data_hex,
			"valueHex": value_hex,
			"gasEstimateHex": gas_estimate_hex,
			"gasPriceWeiHex": gas_price_hex,
			"estimatedFeeWeiHex": estimated_fee_wei_hex,
		}

		return {
			"message": (
				f"Prepared contract interaction for function {functionName} on {chain_key}. "
				"MetaMask confirmation will be requested directly by the wallet."
			),
			"state": "ready_for_wallet",
			"clientAction": "metamask_send_transaction",
			"transactionData": transaction_data,
			"interaction": {
				"mode": "write",
				"contractName": contract.get("contractName") or "(Unnamed)",
				"contractAddress": to_checksum_address(resolved_address),
				"networkName": chain_key,
				"function": functionName,
				"signature": signature,
				"args": args,
				"stateMutability": mutability,
			},
			"source": "metamask",
		}
	except Exception as error:
		return {"error": f"interactWithContract error: {error}", "source": "metamask"}
