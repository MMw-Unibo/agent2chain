from defiUtils import execute_defi_operation
from defiPolicy import enforce_state_changing_defi_knowledge


async def stake(
	networkName: str,
	protocolName: str,
	tokenSymbol: str,
	amount: str,
	userAddress: str,
	knowledgeLevel: str,
	recipientAddress: str = "",
	referralCode: int = 0,
) -> dict:
	"""Prepare a staking transaction for a supported chain/protocol/token."""
	policy_error = enforce_state_changing_defi_knowledge("stake", knowledgeLevel)
	if policy_error:
		return policy_error

	return await execute_defi_operation(
		"stake",
		networkName=networkName,
		protocolName=protocolName,
		tokenSymbol=tokenSymbol,
		amount=amount,
		userAddress=userAddress,
		recipientAddress=recipientAddress,
		referralCode=referralCode,
	)