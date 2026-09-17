import sys
from pathlib import Path

from eth_utils import to_checksum_address

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
	sys.path.append(str(SRC_ROOT))

from defiReadUtils import (
	amount_to_units,
	derive_spender_from_route,
	encode_function_call,
	eth_call_strict,
	format_units,
	resolve_chain_data,
	simulate_write_call,
)
from defiUtils import execute_defi_operation
from utils.supported_tokens import get_operation_route
from utils.tool_utils import is_valid_evm_address


async def precheckOperation(
	networkName: str,
	protocolName: str,
	operation: str,
	tokenSymbol: str,
	amount: str,
	userAddress: str,
) -> dict:
	"""Check DeFi prerequisites (balance, allowance, simulation, collateral/liquidity for local-defi)."""
	try:
		if not is_valid_evm_address(userAddress):
			return {"error": "precheckOperation error: Invalid userAddress", "source": "defi"}

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
				"source": "defi",
			}

		token_cfg = route.get("token") or {}
		decimals = int(token_cfg.get("decimals") or 18)
		amount_units = amount_to_units(amount, decimals)
		chain_key, chain_data = resolve_chain_data(networkName)
		rpc_urls = chain_data.get("rpcUrls") or []
		checks: list[dict] = []
		recommendations: list[str] = []
		can_proceed = True

		if token_cfg.get("isNative"):
			checks.append({
				"name": "native-balance-check",
				"status": "skipped",
				"message": "Native balance precheck not executed in this tool version.",
			})
		else:
			token_address = token_cfg.get("address")
			if not is_valid_evm_address(token_address):
				return {
					"error": "precheckOperation error: Token address missing or invalid in configuration",
					"source": "defi",
				}

			balance_data = encode_function_call("balanceOf(address)", [userAddress])
			balance_raw = eth_call_strict(rpc_urls, str(token_address), balance_data)
			balance_units = int(balance_raw, 16)
			balance_ok = balance_units >= amount_units
			checks.append(
				{
					"name": "token-balance",
					"status": "ok" if balance_ok else "fail",
					"balance": format_units(balance_units, decimals),
					"balanceUnits": str(balance_units),
					"required": amount,
					"requiredUnits": str(amount_units),
				}
			)
			if not balance_ok:
				can_proceed = False
				recommendations.append(
					f"Insufficient {tokenSymbol.upper()} balance for requested {operation} amount"
				)

			requires_approval = bool((route.get("operationMeta") or {}).get("requiresApproval"))
			if requires_approval:
				spender = route.get("approvalTarget") or derive_spender_from_route(
					network_name=networkName,
					protocol_name=protocolName,
					operation=operation,
					token_symbol=tokenSymbol,
				)
				if is_valid_evm_address(spender):
					allowance_data = encode_function_call(
						"allowance(address,address)",
						[userAddress, spender],
					)
					allowance_raw = eth_call_strict(rpc_urls, str(token_address), allowance_data)
					allowance_units = int(allowance_raw, 16)
					allowance_ok = allowance_units >= amount_units
					checks.append(
						{
							"name": "token-allowance",
							"status": "ok" if allowance_ok else "fail",
							"spender": to_checksum_address(spender),
							"allowance": format_units(allowance_units, decimals),
							"allowanceUnits": str(allowance_units),
							"required": amount,
							"requiredUnits": str(amount_units),
						}
					)
					if not allowance_ok:
						can_proceed = False
						recommendations.append(
							f"Run approve for {tokenSymbol.upper()} before {operation}"
						)

		if chain_key == "ganache" and str(route.get("protocolId")) == "local-defi" and operation == "borrow":
			requested_units = amount_units
			lending_pool = None
			try:
				from utils.supported_tokens import get_chain_protocols, resolve_protocol_id
				protocols = get_chain_protocols(networkName)
				protocol_cfg = protocols.get(resolve_protocol_id(protocolName), {})
				lending_pool = (protocol_cfg.get("contracts") or {}).get("lendingPool")
			except Exception:
				lending_pool = None

			if is_valid_evm_address(lending_pool):
				collateral_balance = int(
					eth_call_strict(
						rpc_urls,
						str(lending_pool),
						encode_function_call("collateralBalance(address)", [userAddress]),
					)
					,
					16,
				)
				current_debt = int(
					eth_call_strict(
						rpc_urls,
						str(lending_pool),
						encode_function_call("currentDebt(address)", [userAddress]),
					)
					,
					16,
				)
				max_borrowable = int(
					eth_call_strict(
						rpc_urls,
						str(lending_pool),
						encode_function_call("maxBorrowable(address)", [userAddress]),
					)
					,
					16,
				)
				total_liquidity = int(
					eth_call_strict(
						rpc_urls,
						str(lending_pool),
						encode_function_call("totalLiquidity()", []),
					)
					,
					16,
				)

				available_by_collateral = max(0, max_borrowable - current_debt)
				collateral_ok = available_by_collateral >= requested_units
				liquidity_ok = total_liquidity >= requested_units
				checks.append(
					{
						"name": "local-defi-collateral-health",
						"status": "ok" if collateral_ok else "fail",
						"collateralBalanceUnits": str(collateral_balance),
						"currentDebtUnits": str(current_debt),
						"maxBorrowableUnits": str(max_borrowable),
						"remainingBorrowableUnits": str(available_by_collateral),
					}
				)
				checks.append(
					{
						"name": "local-defi-pool-liquidity",
						"status": "ok" if liquidity_ok else "fail",
						"totalLiquidityUnits": str(total_liquidity),
						"requiredUnits": str(requested_units),
					}
				)
				if not collateral_ok:
					can_proceed = False
					recommendations.append("Deposit more collateral before borrowing")
				if not liquidity_ok:
					can_proceed = False
					recommendations.append("Provide pool liquidity (lend) before borrowing")

		prepared = await execute_defi_operation(
			operation,
			networkName=networkName,
			protocolName=protocolName,
			tokenSymbol=tokenSymbol,
			amount=amount,
			userAddress=userAddress,
		)
		if prepared.get("transactionData"):
			tx_data = prepared["transactionData"]
			sim_ok, sim_error = simulate_write_call(
				rpc_urls,
				from_address=userAddress,
				to_address=str(tx_data.get("to")),
				data_hex=str(tx_data.get("data") or "0x"),
				value_hex=str(tx_data.get("valueHex") or "0x0"),
			)
			checks.append(
				{
					"name": "eth-call-simulation",
					"status": "ok" if sim_ok else "fail",
					"error": sim_error,
				}
			)
			if not sim_ok:
				can_proceed = False
				recommendations.append(
					"Simulation failed. Review revert reason before sending transaction"
				)

		return {
			"network": chain_key,
			"protocol": protocolName,
			"operation": operation,
			"token": tokenSymbol.upper(),
			"amount": amount,
			"amountUnits": str(amount_units),
			"canProceed": can_proceed,
			"checks": checks,
			"recommendations": recommendations,
			"source": "defi",
		}
	except Exception as error:
		return {"error": f"precheckOperation error: {error}", "source": "defi"}
