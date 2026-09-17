from utils.tool_utils import filter_contract_records, load_contract_registry


async def listDeployedContracts(
	userAddress: str = "",
	networkName: str = "",
) -> dict:
	"""List deployed contracts from local registry, with optional filters."""
	try:
		contracts = filter_contract_records(
			load_contract_registry(__file__),
			user_address=userAddress,
			network_name=networkName,
		)

		if not contracts:
			return {
				"message": "No contracts have been deployed yet.",
				"count": 0,
				"contracts": [],
				"source": "local-registry",
			}

		simplified = []
		for record in contracts:
			simplified.append(
				{
					"contractName": record.get("contractName") or "(Unnamed)",
					"contractAddress": record.get("contractAddress"),
					"networkName": record.get("networkName"),
					"deployTxHash": record.get("deployTxHash"),
					"userAddress": record.get("userAddress"),
					"savedAt": record.get("savedAt"),
				}
			)

		lines = [
			f"• {item['contractName']} @ {item['contractAddress']} [{item['networkName']}] (tx: {item['deployTxHash']})"
			for item in simplified
		]

		return {
			"message": "Deployed contracts found.",
			"count": len(simplified),
			"summary": "\n".join(lines),
			"contracts": simplified,
			"source": "local-registry",
		}
	except Exception as error:
		return {
			"error": f"listDeployedContracts error: {error}",
			"source": "local-registry",
		}
