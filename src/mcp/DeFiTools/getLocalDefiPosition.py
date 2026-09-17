import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
	sys.path.append(str(SRC_ROOT))

from defiReadUtils import encode_function_call, eth_call_strict, format_units, resolve_chain_data
from utils.supported_tokens import get_chain_protocols, resolve_protocol_id
from utils.tool_utils import is_valid_evm_address


async def getLocalDefiPosition(
	networkName: str,
	protocolName: str,
	userAddress: str,
	collateralTokenSymbol: str = "TKA",
	borrowTokenSymbol: str = "TKB",
) -> dict:
	"""Read local-defi lending and staking position data for a user (Ganache-focused)."""
	try:
		if not is_valid_evm_address(userAddress):
			return {"error": "getLocalDefiPosition error: Invalid userAddress", "source": "defi"}

		chain_key, chain_data = resolve_chain_data(networkName)
		rpc_urls = chain_data.get("rpcUrls") or []
		protocols = get_chain_protocols(networkName)
		protocol = protocols.get(resolve_protocol_id(protocolName))
		if not protocol:
			return {
				"error": f"Protocol {protocolName} not configured on {networkName}",
				"source": "defi",
			}

		contracts = protocol.get("contracts") or {}
		lending_pool = contracts.get("lendingPool")
		staking_vault = contracts.get("stakingVault")

		if not is_valid_evm_address(lending_pool):
			return {
				"error": "getLocalDefiPosition error: lendingPool address missing/invalid in config",
				"source": "defi",
			}

		collateral_balance = int(
			eth_call_strict(
				rpc_urls,
				str(lending_pool),
				encode_function_call("collateralBalance(address)", [userAddress]),
			),
			16,
		)
		current_debt = int(
			eth_call_strict(
				rpc_urls,
				str(lending_pool),
				encode_function_call("currentDebt(address)", [userAddress]),
			),
			16,
		)
		max_borrowable = int(
			eth_call_strict(
				rpc_urls,
				str(lending_pool),
				encode_function_call("maxBorrowable(address)", [userAddress]),
			),
			16,
		)
		total_liquidity = int(
			eth_call_strict(
				rpc_urls,
				str(lending_pool),
				encode_function_call("totalLiquidity()", []),
			),
			16,
		)
		user_liquidity = int(
			eth_call_strict(
				rpc_urls,
				str(lending_pool),
				encode_function_call("liquidityProvided(address)", [userAddress]),
			),
			16,
		)

		remaining_borrowable = max(0, max_borrowable - current_debt)
		position = {
			"network": chain_key,
			"protocol": protocolName,
			"user": userAddress,
			"lending": {
				"collateralBalanceUnits": str(collateral_balance),
				"collateralBalance": format_units(collateral_balance, 18),
				"collateralTokenSymbol": collateralTokenSymbol.upper(),
				"currentDebtUnits": str(current_debt),
				"currentDebt": format_units(current_debt, 18),
				"borrowTokenSymbol": borrowTokenSymbol.upper(),
				"maxBorrowableUnits": str(max_borrowable),
				"maxBorrowable": format_units(max_borrowable, 18),
				"remainingBorrowableUnits": str(remaining_borrowable),
				"remainingBorrowable": format_units(remaining_borrowable, 18),
				"totalPoolLiquidityUnits": str(total_liquidity),
				"totalPoolLiquidity": format_units(total_liquidity, 18),
				"userLiquidityProvidedUnits": str(user_liquidity),
				"userLiquidityProvided": format_units(user_liquidity, 18),
			},
		}

		if is_valid_evm_address(staking_vault):
			tokens = protocol.get("tokens") or {}
			collateral_token = tokens.get(collateralTokenSymbol.upper(), {})
			collateral_token_address = collateral_token.get("address")
			if is_valid_evm_address(collateral_token_address):
				raw = eth_call_strict(
					rpc_urls,
					str(staking_vault),
					encode_function_call(
						"tokenPositions(address,address)",
						[userAddress, collateral_token_address],
					),
				)
				from eth_abi import decode as abi_decode
				decoded = abi_decode(["uint256", "uint256", "uint256"], bytes.fromhex(raw[2:]))
				position["staking"] = {
					"token": collateralTokenSymbol.upper(),
					"principalUnits": str(int(decoded[0])),
					"principal": format_units(int(decoded[0]), int(collateral_token.get("decimals") or 18)),
					"rewardsAccruedUnits": str(int(decoded[1])),
					"rewardsAccrued": format_units(int(decoded[1]), int(collateral_token.get("decimals") or 18)),
					"lastUpdate": int(decoded[2]),
				}

		return {**position, "source": "defi"}
	except Exception as error:
		return {"error": f"getLocalDefiPosition error: {error}", "source": "defi"}
