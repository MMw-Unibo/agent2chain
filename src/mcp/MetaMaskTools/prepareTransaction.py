import sys
from decimal import InvalidOperation
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
	sys.path.append(str(SRC_ROOT))

from utils.tool_utils import (
	decimal_to_wei_hex,
	estimate_fee_hex,
	is_valid_evm_address,
	parse_decimal_amount,
	resolve_chain,
)


async def prepareTransaction(
	address: str,
	to: str,
	amount: str,
	networkName: str,
) -> dict:
	"""Prepare a real MetaMask transaction payload for the connected UI wallet."""
	try:
		if not is_valid_evm_address(address):
			return {"error": "prepareTransaction error: Invalid sender address", "source": "metamask"}

		if not is_valid_evm_address(to):
			return {"error": "prepareTransaction error: Invalid recipient address", "source": "metamask"}

		try:
			amount_value = parse_decimal_amount(amount, allow_zero=False)
			value_hex = decimal_to_wei_hex(amount_value, allow_zero=False)
		except (InvalidOperation, ValueError):
			return {"error": "prepareTransaction error: Invalid amount", "source": "metamask"}

		chain_key, chain_data = resolve_chain(networkName)
		if not chain_data:
			return {"error": f"prepareTransaction error: Unknown network: {networkName}", "source": "metamask"}

		tx_for_estimate = {
			"from": address,
			"to": to,
			"value": value_hex,
		}
		gas_estimate_hex, gas_price_hex, estimated_fee_wei_hex = estimate_fee_hex(
			chain_data.get("rpcUrls", []),
			tx_for_estimate,
			timeout=8,
		)

		transaction_data = {
			"from": address,
			"to": to,
			"amount": str(amount_value),
			"chainName": chain_key,
			"networkName": chain_key,
			"chainId": chain_data["chainId"],
			"chainIdHex": hex(chain_data["chainId"]),
			"symbol": chain_data["symbol"],
			"rpcUrls": chain_data.get("rpcUrls", []),
			"valueHex": value_hex,
			"gasEstimateHex": gas_estimate_hex,
			"gasPriceWeiHex": gas_price_hex,
			"estimatedFeeWeiHex": estimated_fee_wei_hex,
		}

		message = (
			f"Transaction prepared: send {amount_value} {chain_data['symbol']} "
			f"from {address} to {to} on {chain_key}. "
			"MetaMask confirmation will be requested directly by the wallet."
		)
		return {
			"message": message,
			"state": "ready_for_wallet",
			"clientAction": "metamask_send_transaction",
			"transactionData": transaction_data,
			"source": "metamask",
		}
	except Exception as error:
		return {"error": f"prepareTransaction error: {error}", "source": "metamask"}
