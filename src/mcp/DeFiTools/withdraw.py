from defiUtils import execute_defi_operation
from defiPolicy import enforce_state_changing_defi_knowledge


async def withdraw(
	networkName: str,
	protocolName: str,
	tokenSymbol: str,
	amount: str,
	userAddress: str,
	knowledgeLevel: str,
	recipientAddress: str = "",
) -> dict:
	"""Prepare a DeFi withdraw transaction for a supported route."""
	policy_error = enforce_state_changing_defi_knowledge("withdraw", knowledgeLevel)
	if policy_error:
		return policy_error

	return await execute_defi_operation(
		"withdraw",
		networkName=networkName,
		protocolName=protocolName,
		tokenSymbol=tokenSymbol,
		amount=amount,
		userAddress=userAddress,
		recipientAddress=recipientAddress,
	)