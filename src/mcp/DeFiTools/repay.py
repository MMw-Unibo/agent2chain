from defiUtils import execute_defi_operation
from defiPolicy import enforce_state_changing_defi_knowledge


async def repay(
	networkName: str,
	protocolName: str,
	tokenSymbol: str,
	amount: str,
	userAddress: str,
	knowledgeLevel: str,
	rateMode: int = 2,
	recipientAddress: str = "",
) -> dict:
	"""Prepare a DeFi repay transaction for a supported route."""
	policy_error = enforce_state_changing_defi_knowledge("repay", knowledgeLevel)
	if policy_error:
		return policy_error

	return await execute_defi_operation(
		"repay",
		networkName=networkName,
		protocolName=protocolName,
		tokenSymbol=tokenSymbol,
		amount=amount,
		userAddress=userAddress,
		rateMode=rateMode,
		recipientAddress=recipientAddress,
	)