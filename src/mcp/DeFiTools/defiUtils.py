from __future__ import annotations

import re
import sys
from decimal import InvalidOperation
from pathlib import Path

from eth_abi import encode as abi_encode
from eth_utils import keccak, to_checksum_address

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
	sys.path.append(str(SRC_ROOT))

from utils.supported_tokens import (
	get_operation_route,
	list_supported_operations,
	list_supported_protocols,
)
from utils.tool_utils import (
	estimate_fee_hex,
	is_valid_evm_address,
	parse_decimal_amount,
	resolve_chain,
)


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
METHOD_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\((.*)\)\s*$")


def _parse_method_signature(signature: str) -> tuple[str, list[str]]:
	match = METHOD_RE.match(str(signature or "").strip())
	if not match:
		raise ValueError(f"Invalid method signature: {signature}")

	name = match.group(1)
	raw_args = match.group(2).strip()
	if not raw_args:
		return name, []

	types = [part.strip() for part in raw_args.split(",") if part.strip()]
	return name, types


def _to_token_units(amount: str, decimals: int | None) -> int:
	decimals_value = int(decimals if decimals is not None else 18)
	if decimals_value < 0 or decimals_value > 36:
		raise ValueError("Invalid token decimals")

	amount_decimal = parse_decimal_amount(amount, allow_zero=False)
	scaled = amount_decimal * (10 ** decimals_value)
	if scaled != scaled.to_integral_value():
		raise ValueError(f"Amount supports at most {decimals_value} decimals for selected token")

	amount_units = int(scaled)
	if amount_units <= 0:
		raise ValueError("Amount must be positive")
	return amount_units


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


def _signature_from_parts(function_name: str, input_types: list[str]) -> str:
	return f"{function_name}({','.join(input_types)})"


def _resolve_token_address(token: dict) -> str:
	if token.get("isNative"):
		return ZERO_ADDRESS

	address = token.get("address")
	if not is_valid_evm_address(address):
		raise ValueError("Selected token does not have a valid ERC20 address configured")
	return to_checksum_address(address)


def _build_operation_args(
	*,
	function_name: str,
	input_types: list[str],
	token: dict,
	amount_units: int,
	user_address: str,
	recipient_address: str,
	rate_mode: int,
	referral_code: int,
) -> list:
	token_address = _resolve_token_address(token)
	recipient = recipient_address if is_valid_evm_address(recipient_address) else user_address

	if function_name == "submit" and input_types == ["address"]:
		return [recipient]

	if function_name == "supply" and len(input_types) == 4:
		return [token_address, amount_units, user_address, int(referral_code)]

	if function_name == "borrow" and len(input_types) == 5:
		return [token_address, amount_units, int(rate_mode), int(referral_code), user_address]

	if function_name == "repay" and len(input_types) == 4:
		return [token_address, amount_units, int(rate_mode), user_address]

	if function_name == "withdraw" and len(input_types) == 3:
		return [token_address, amount_units, recipient]

	if function_name in {"supply", "withdraw"} and len(input_types) == 2:
		return [token_address, amount_units]

	if function_name in {"stake", "deposit", "lend", "borrow"} and len(input_types) == 2:
		return [token_address, amount_units]

	if function_name in {"mint", "borrow", "repayBorrow", "redeemUnderlying"} and len(input_types) == 1:
		if not input_types[0].startswith("uint") and not input_types[0].startswith("int"):
			raise ValueError("Unsupported method signature for single-argument operation")
		return [amount_units]

	# Generic fallback for custom routes.
	args: list = []
	amount_used = False
	for index, abi_type in enumerate(input_types):
		if abi_type == "address":
			if index == 0:
				args.append(token_address)
			else:
				args.append(recipient)
			continue

		if abi_type.startswith("uint") or abi_type.startswith("int"):
			if not amount_used:
				args.append(amount_units)
				amount_used = True
			else:
				args.append(0)
			continue

		if abi_type == "bool":
			args.append(False)
			continue

		if abi_type == "string":
			args.append("")
			continue

		if abi_type.startswith("bytes"):
			args.append("0x")
			continue

		raise ValueError(f"Unsupported ABI argument type in generic mapper: {abi_type}")

	return args


def _build_approval_calldata(spender: str, amount_units: int) -> str:
	selector = keccak(text="approve(address,uint256)")[:4]
	encoded = abi_encode(["address", "uint256"], [to_checksum_address(spender), int(amount_units)])
	return f"0x{(selector + encoded).hex()}"


async def execute_defi_operation(
	operation: str,
	*,
	networkName: str,
	protocolName: str,
	tokenSymbol: str,
	amount: str = "0",
	userAddress: str,
	recipientAddress: str = "",
	rateMode: int = 2,
	referralCode: int = 0,
) -> dict:
	"""Prepare a DeFi contract transaction according to supported_tokens routing config."""
	try:
		if not networkName or not str(networkName).strip():
			return {"error": "Missing networkName", "source": "defi"}
		if not protocolName or not str(protocolName).strip():
			return {"error": "Missing protocolName", "source": "defi"}
		if not tokenSymbol or not str(tokenSymbol).strip():
			return {"error": "Missing tokenSymbol", "source": "defi"}
		if not userAddress or not is_valid_evm_address(userAddress):
			return {"error": "Invalid userAddress", "source": "defi"}

		route = get_operation_route(
			network_name=networkName,
			protocol_name=protocolName,
			operation=operation,
			token_symbol=tokenSymbol,
		)
		if not route:
			return {
				"error": (
					f"Unsupported DeFi route for {operation} on network={networkName}, "
					f"protocol={protocolName}, token={tokenSymbol}"
				),
				"supportedProtocols": list_supported_protocols(networkName),
				"supportedOperations": list_supported_operations(networkName, protocolName),
				"source": "defi",
			}

		contract_address = route.get("contractAddress")
		if not is_valid_evm_address(contract_address):
			return {
				"error": "Operation contract address is missing or invalid in configuration",
				"route": route,
				"source": "defi",
			}

		token_cfg = route.get("token") if isinstance(route.get("token"), dict) else None
		if not token_cfg:
			return {
				"error": "Token is not configured for this operation route",
				"route": route,
				"source": "defi",
			}

		method_signature = str(route.get("method") or "").strip()
		function_name, input_types = _parse_method_signature(method_signature)

		requires_amount = any(
			abi_type.startswith("uint") or abi_type.startswith("int")
			for abi_type in input_types
		) or function_name == "submit"

		if requires_amount:
			try:
				amount_units = _to_token_units(amount, token_cfg.get("decimals"))
			except (InvalidOperation, ValueError) as amount_error:
				return {"error": f"Invalid amount: {amount_error}", "source": "defi"}
		else:
			amount_units = 0

		raw_args = _build_operation_args(
			function_name=function_name,
			input_types=input_types,
			token=token_cfg,
			amount_units=amount_units,
			user_address=to_checksum_address(userAddress),
			recipient_address=to_checksum_address(recipientAddress) if is_valid_evm_address(recipientAddress) else "",
			rate_mode=int(rateMode),
			referral_code=int(referralCode),
		)
		normalized_args = [
			_normalize_type_value(input_types[index], raw_args[index])
			for index in range(len(input_types))
		]

		signature = _signature_from_parts(function_name, input_types)
		selector = keccak(text=signature)[:4]
		encoded_args = abi_encode(input_types, normalized_args) if input_types else b""
		data_hex = f"0x{(selector + encoded_args).hex()}"

		chain_key = route.get("chain")
		_, chain_data = resolve_chain(str(chain_key))
		if not chain_data:
			return {
				"error": f"Unable to resolve chain metadata for {chain_key}",
				"source": "defi",
			}

		rpc_urls = chain_data.get("rpcUrls") or []
		if not rpc_urls:
			return {
				"error": f"No RPC URL configured for network {chain_key}",
				"source": "defi",
			}

		value_hex = "0x0"
		if token_cfg.get("isNative") and function_name == "submit":
			value_hex = hex(int(amount_units))

		tx_for_estimate = {
			"from": to_checksum_address(userAddress),
			"to": to_checksum_address(contract_address),
			"data": data_hex,
		}
		if value_hex != "0x0":
			tx_for_estimate["value"] = value_hex

		gas_estimate_hex, gas_price_hex, estimated_fee_wei_hex = estimate_fee_hex(
			rpc_urls,
			tx_for_estimate,
			timeout=10,
		)

		approval_target = route.get("approvalTarget")
		token_address = token_cfg.get("address")
		requires_approval = bool((route.get("operationMeta") or {}).get("requiresApproval"))
		approval = None
		if (
			requires_approval
			and not token_cfg.get("isNative")
			and is_valid_evm_address(approval_target)
			and is_valid_evm_address(token_address)
		):
			approval = {
				"spender": to_checksum_address(approval_target),
				"tokenAddress": to_checksum_address(token_address),
				"amountUnits": str(amount_units),
				"approveData": _build_approval_calldata(str(approval_target), amount_units),
			}

		transaction_data = {
			"from": to_checksum_address(userAddress),
			"to": to_checksum_address(contract_address),
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
				f"Prepared DeFi transaction for {operation} on {route.get('protocolName')} "
				f"({chain_key}) with token {tokenSymbol.upper()}."
			),
			"state": "ready_for_wallet",
			"clientAction": "metamask_send_transaction",
			"transactionData": transaction_data,
			"defi": {
				"operation": operation,
				"protocolId": route.get("protocolId"),
				"protocolName": route.get("protocolName"),
				"token": tokenSymbol.upper(),
				"tokenAddress": token_address,
				"tokenDecimals": token_cfg.get("decimals"),
				"amount": str(amount if requires_amount else "0"),
				"amountUnits": str(amount_units),
				"contractRef": route.get("contractRef"),
				"method": method_signature,
				"signature": signature,
				"arguments": raw_args,
				"notes": route.get("notes"),
				"approval": approval,
			},
			"source": "defi",
		}
	except Exception as error:
		return {"error": f"{operation} error: {error}", "source": "defi"}