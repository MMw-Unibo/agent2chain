import sys
from pathlib import Path

from eth_utils import to_checksum_address

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
	sys.path.append(str(SRC_ROOT))

from defiReadUtils import (
	parse_amount_or_max,
	prepare_approve_transaction,
	resolve_token_config,
	derive_spender_from_route,
)
from defiPolicy import enforce_state_changing_defi_knowledge
from utils.tool_utils import is_valid_evm_address


async def approve(
	networkName: str,
	tokenSymbol: str,
	userAddress: str,
	knowledgeLevel: str,
	amount: str = "max",
	spenderAddress: str = "",
	protocolName: str = "",
	operation: str = "",
) -> dict:
	"""Prepare an ERC20 approve transaction for a DeFi operation."""
	try:
		policy_error = enforce_state_changing_defi_knowledge("approve", knowledgeLevel)
		if policy_error:
			return policy_error

		if not is_valid_evm_address(userAddress):
			return {"error": "approve error: Invalid userAddress", "source": "defi"}

		token_cfg = resolve_token_config(networkName, tokenSymbol, protocolName or None)
		if token_cfg.get("isNative"):
			return {"error": "approve error: Native tokens do not support ERC20 approve", "source": "defi"}

		token_address = token_cfg.get("address")
		if not is_valid_evm_address(token_address):
			return {
				"error": "approve error: Token address missing or invalid in configuration",
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
					"approve error: spenderAddress is required or must be derivable from "
					"protocolName+operation route"
				),
				"source": "defi",
			}

		amount_units = parse_amount_or_max(amount, int(token_cfg.get("decimals") or 18))
		transaction_data = prepare_approve_transaction(
			network_name=networkName,
			user_address=userAddress,
			token_address=str(token_address),
			spender_address=resolved_spender,
			amount_units=amount_units,
		)

		return {
			"message": (
				f"Prepared approve transaction for {tokenSymbol.upper()} spender "
				f"{to_checksum_address(resolved_spender)}."
			),
			"state": "ready_for_wallet",
			"clientAction": "metamask_send_transaction",
			"transactionData": transaction_data,
			"approval": {
				"token": tokenSymbol.upper(),
				"tokenAddress": to_checksum_address(str(token_address)),
				"spender": to_checksum_address(resolved_spender),
				"amount": amount,
				"amountUnits": str(amount_units),
				"protocol": protocolName or None,
				"operation": operation or None,
			},
			"source": "defi",
		}
	except Exception as error:
		return {"error": f"approve error: {error}", "source": "defi"}
