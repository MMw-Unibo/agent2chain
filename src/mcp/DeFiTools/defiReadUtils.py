from __future__ import annotations

import sys
from decimal import InvalidOperation
from pathlib import Path

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import keccak, to_checksum_address

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
	sys.path.append(str(SRC_ROOT))

from utils.supported_tokens import get_operation_route, list_supported_tokens
from utils.tool_utils import (
	estimate_fee_hex,
	is_valid_evm_address,
	parse_decimal_amount,
	rpc_call_with_fallback_strict,
	resolve_chain,
)

MAX_UINT256 = (1 << 256) - 1


def parse_signature(signature: str) -> tuple[str, list[str]]:
	raw = str(signature or "").strip()
	if "(" not in raw or not raw.endswith(")"):
		raise ValueError(f"Invalid function signature: {signature}")

	name = raw[: raw.index("(")].strip()
	inner = raw[raw.index("(") + 1 : -1].strip()
	if not name:
		raise ValueError(f"Invalid function signature: {signature}")
	if not inner:
		return name, []

	types = [part.strip() for part in inner.split(",") if part.strip()]
	return name, types


def encode_function_call(signature: str, args: list) -> str:
	_, input_types = parse_signature(signature)
	selector = keccak(text=signature)[:4]
	encoded_args = abi_encode(input_types, args) if input_types else b""
	return f"0x{(selector + encoded_args).hex()}"


def decode_uint256(raw_result: str) -> int:
	raw_hex = raw_result[2:] if str(raw_result).startswith("0x") else str(raw_result)
	raw_bytes = bytes.fromhex(raw_hex)
	decoded = abi_decode(["uint256"], raw_bytes)
	return int(decoded[0])


def decode_types(raw_result: str, output_types: list[str]) -> list:
	raw_hex = raw_result[2:] if str(raw_result).startswith("0x") else str(raw_result)
	raw_bytes = bytes.fromhex(raw_hex)
	decoded = abi_decode(output_types, raw_bytes)
	result: list = []
	for item in decoded:
		if isinstance(item, bytes):
			result.append(f"0x{item.hex()}")
		elif isinstance(item, tuple):
			result.append(list(item))
		else:
			result.append(item)
	return result


def format_units(amount_units: int, decimals: int) -> str:
	if decimals <= 0:
		return str(amount_units)

	sign = "-" if amount_units < 0 else ""
	value = abs(int(amount_units))
	base = 10 ** decimals
	whole = value // base
	fraction = value % base
	if fraction == 0:
		return f"{sign}{whole}"

	fraction_text = str(fraction).rjust(decimals, "0").rstrip("0")
	return f"{sign}{whole}.{fraction_text}"


def amount_to_units(amount: str, decimals: int) -> int:
	amount_decimal = parse_decimal_amount(amount, allow_zero=False)
	scaled = amount_decimal * (10 ** int(decimals))
	if scaled != scaled.to_integral_value():
		raise ValueError(f"Amount supports at most {decimals} decimals")
	units = int(scaled)
	if units <= 0:
		raise ValueError("Amount must be positive")
	return units


def resolve_chain_data(network_name: str) -> tuple[str, dict]:
	chain_key, chain_data = resolve_chain(network_name)
	if not chain_data:
		raise ValueError(f"Unknown network: {network_name}")

	rpc_urls = chain_data.get("rpcUrls") or []
	if not rpc_urls:
		raise ValueError(f"No RPC URL configured for network {chain_key}")

	return chain_key, chain_data


def resolve_token_config(network_name: str, token_symbol: str, protocol_name: str | None = None) -> dict:
	tokens = list_supported_tokens(network_name, protocol_name)
	token = tokens.get(str(token_symbol or "").upper()) if isinstance(tokens, dict) else None
	if not token:
		raise ValueError(
			f"Token {token_symbol} is not configured for network={network_name} protocol={protocol_name or '(any)'}"
		)
	return token


def eth_call_strict(rpc_urls: list[str], to_address: str, data_hex: str, from_address: str | None = None):
	tx = {
		"to": to_checksum_address(to_address),
		"data": data_hex,
	}
	if from_address and is_valid_evm_address(from_address):
		tx["from"] = to_checksum_address(from_address)

	result, error = rpc_call_with_fallback_strict(
		rpc_urls,
		"eth_call",
		[tx, "latest"],
		timeout=12,
	)
	if not isinstance(result, str):
		raise ValueError(f"eth_call failed: {error}")
	return result


def read_uint256_call(
	rpc_urls: list[str],
	to_address: str,
	signature: str,
	args: list,
	from_address: str | None = None,
) -> int:
	data = encode_function_call(signature, args)
	raw = eth_call_strict(rpc_urls, to_address, data, from_address)
	return decode_uint256(raw)


def simulate_write_call(
	rpc_urls: list[str],
	from_address: str,
	to_address: str,
	data_hex: str,
	value_hex: str = "0x0",
) -> tuple[bool, str | None]:
	tx = {
		"from": to_checksum_address(from_address),
		"to": to_checksum_address(to_address),
		"data": data_hex,
	}
	if value_hex and value_hex != "0x0":
		tx["value"] = value_hex

	result, error = rpc_call_with_fallback_strict(
		rpc_urls,
		"eth_call",
		[tx, "latest"],
		timeout=12,
	)
	if error is not None or result is None:
		return False, str(error)
	return True, None


def derive_spender_from_route(
	network_name: str,
	protocol_name: str,
	operation: str,
	token_symbol: str,
) -> str | None:
	route = get_operation_route(
		network_name=network_name,
		protocol_name=protocol_name,
		operation=operation,
		token_symbol=token_symbol,
	)
	if not route:
		return None
	spender = route.get("approvalTarget")
	if spender and is_valid_evm_address(spender):
		return to_checksum_address(spender)
	return None


def prepare_approve_transaction(
	*,
	network_name: str,
	user_address: str,
	token_address: str,
	spender_address: str,
	amount_units: int,
) -> dict:
	chain_key, chain_data = resolve_chain_data(network_name)
	rpc_urls = chain_data.get("rpcUrls") or []
	data_hex = encode_function_call(
		"approve(address,uint256)",
		[to_checksum_address(spender_address), int(amount_units)],
	)

	tx_for_estimate = {
		"from": to_checksum_address(user_address),
		"to": to_checksum_address(token_address),
		"data": data_hex,
	}
	gas_estimate_hex, gas_price_hex, estimated_fee_wei_hex = estimate_fee_hex(
		rpc_urls,
		tx_for_estimate,
		timeout=10,
	)

	return {
		"from": to_checksum_address(user_address),
		"to": to_checksum_address(token_address),
		"networkName": chain_key,
		"chainName": chain_key,
		"chainId": chain_data.get("chainId"),
		"chainIdHex": hex(int(chain_data["chainId"])),
		"symbol": chain_data.get("symbol"),
		"rpcUrls": rpc_urls,
		"data": data_hex,
		"valueHex": "0x0",
		"gasEstimateHex": gas_estimate_hex,
		"gasPriceWeiHex": gas_price_hex,
		"estimatedFeeWeiHex": estimated_fee_wei_hex,
	}


def parse_amount_or_max(amount: str, decimals: int) -> int:
	raw = str(amount or "").strip().lower()
	if raw in {"max", "infinite", "infinity", "unlimited"}:
		return MAX_UINT256
	try:
		return amount_to_units(amount, decimals)
	except (InvalidOperation, ValueError) as error:
		raise ValueError(f"Invalid amount: {error}")
