from defiUtils import execute_defi_operation
from defiPolicy import enforce_state_changing_defi_knowledge


async def claimRewards(
	networkName: str,
	protocolName: str,
	tokenSymbol: str,
	userAddress: str,
	knowledgeLevel: str,
) -> dict:
	"""Prepare a transaction to claim staking rewards for a supported route."""
	policy_error = enforce_state_changing_defi_knowledge("claim-rewards", knowledgeLevel)
	if policy_error:
		return policy_error

	return await execute_defi_operation(
		"claim-rewards",
		networkName=networkName,
		protocolName=protocolName,
		tokenSymbol=tokenSymbol,
		userAddress=userAddress,
	)