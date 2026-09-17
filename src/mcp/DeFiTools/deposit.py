from defiUtils import execute_defi_operation
from defiPolicy import enforce_state_changing_defi_knowledge


async def deposit(
	networkName: str,
	protocolName: str,
	tokenSymbol: str,
	amount: str,
	userAddress: str,
	knowledgeLevel: str,
	recipientAddress: str = "",
	referralCode: int = 0,
) -> dict:
	"""Prepare a lending deposit transaction for a supported route."""
	policy_error = enforce_state_changing_defi_knowledge("deposit", knowledgeLevel)
	if policy_error:
		return policy_error

	return await execute_defi_operation(
		"deposit",
		networkName=networkName,
		protocolName=protocolName,
		tokenSymbol=tokenSymbol,
		amount=amount,
		userAddress=userAddress,
		recipientAddress=recipientAddress,
		referralCode=referralCode,
	)