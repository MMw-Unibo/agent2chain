from defiUtils import execute_defi_operation
from defiPolicy import enforce_state_changing_defi_knowledge


async def lend(
	networkName: str,
	protocolName: str,
	tokenSymbol: str,
	amount: str,
	userAddress: str,
	knowledgeLevel: str,
	recipientAddress: str = "",
	referralCode: int = 0,
) -> dict:
	"""Prepare a lending liquidity-provision transaction for a supported route."""
	policy_error = enforce_state_changing_defi_knowledge("lend", knowledgeLevel)
	if policy_error:
		return policy_error

	return await execute_defi_operation(
		"lend",
		networkName=networkName,
		protocolName=protocolName,
		tokenSymbol=tokenSymbol,
		amount=amount,
		userAddress=userAddress,
		recipientAddress=recipientAddress,
		referralCode=referralCode,
	)