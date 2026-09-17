from defiUtils import execute_defi_operation
from defiPolicy import enforce_state_changing_defi_knowledge


async def borrow(
	networkName: str,
	protocolName: str,
	tokenSymbol: str,
	amount: str,
	userAddress: str,
	knowledgeLevel: str,
	rateMode: int = 2,
	recipientAddress: str = "",
	referralCode: int = 0,
) -> dict:
	"""Prepare a DeFi borrow transaction for a supported route."""
	policy_error = enforce_state_changing_defi_knowledge("borrow", knowledgeLevel)
	if policy_error:
		return policy_error

	return await execute_defi_operation(
		"borrow",
		networkName=networkName,
		protocolName=protocolName,
		tokenSymbol=tokenSymbol,
		amount=amount,
		userAddress=userAddress,
		rateMode=rateMode,
		recipientAddress=recipientAddress,
		referralCode=referralCode,
	)