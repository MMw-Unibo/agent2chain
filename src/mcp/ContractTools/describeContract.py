from utils.tool_utils import filter_contract_records, load_contract_registry


def _format_inputs(inputs: list[dict] | None) -> str:
	if not inputs:
		return "—"
	return ", ".join(f"{item.get('name') or '_'}:{item.get('type') or 'unknown'}" for item in inputs)


def _build_param_template(inputs: list[dict] | None) -> dict:
	template = {}
	for item in inputs or []:
		key = item.get("name") or item.get("type") or "param"
		template[key] = item.get("type") or "unknown"
	return template


def _build_formatted_summary(contract: dict, functions: list[dict], total_functions: int) -> str:
	"""Create a UI-friendly markdown summary for contract descriptions."""
	name = contract.get("contractName") or "(Unnamed Contract)"
	address = contract.get("contractAddress") or "N/A"
	network = contract.get("networkName") or "N/A"

	lines = [
		f"## Contract: {name}",
		f"- Address: `{address}`",
		f"- Network: `{network}`",
		f"- Functions: `{total_functions}` total, `{len(functions)}` shown",
		"",
		"## Functions",
	]

	for fn in functions:
		lines.append(
			f"- `{fn.get('signature')}` ({fn.get('mutability')})"
			f" - Inputs: {fn.get('inputs')} - Outputs: {fn.get('outputs')}"
		)

	return "\n".join(lines)


async def describeContract(
	contractAddress: str = "",
	contractName: str = "",
	networkName: str = "",
	userAddress: str = "",
	limit: int = 10,
) -> dict:
	"""Describe deployed contract functions and parameters from local registry."""
	try:
		records = filter_contract_records(
			load_contract_registry(__file__),
			user_address=userAddress,
			network_name=networkName,
			contract_address=contractAddress,
			contract_name=contractName,
		)

		if not records:
			return {
				"message": "No contracts have been deployed yet.",
				"source": "local-registry",
			}

		if len(records) > 1:
			preview = [
				f"• {r.get('contractName') or '(Unnamed)'} @ {r.get('contractAddress') or 'N/A'} [{r.get('networkName') or 'N/A'}]"
				for r in records[:20]
			]
			return {
				"message": f"More contracts match the request ({len(records)}). Specify contractAddress.",
				"matches": len(records),
				"preview": preview,
				"source": "local-registry",
			}

		contract = records[0]
		abi = contract.get("abi") if isinstance(contract.get("abi"), list) else []
		if not abi:
			return {
				"message": "No ABI found for this contract.",
				"contract": {
					"contractName": contract.get("contractName") or "(Unnamed Contract)",
					"contractAddress": contract.get("contractAddress"),
					"networkName": contract.get("networkName"),
					"userAddress": contract.get("userAddress"),
				},
				"source": "local-registry",
			}

		max_items = max(1, min(int(limit or 10), 50))
		functions = [item for item in abi if item.get("type") == "function"]

		function_descriptions = []
		for fn in functions[:max_items]:
			inputs = fn.get("inputs") or []
			outputs = fn.get("outputs") or []
			mutability = fn.get("stateMutability") or ("view" if fn.get("constant") else "nonpayable")

			signature = f"{fn.get('name')}({','.join((i.get('type') or 'unknown') for i in inputs)})"
			function_descriptions.append(
				{
					"name": fn.get("name"),
					"signature": signature,
					"inputs": _format_inputs(inputs),
					"outputs": ", ".join((o.get("type") or "unknown") for o in outputs) or "—",
					"mutability": mutability,
					"paramTemplate": _build_param_template(inputs),
					"positionalOrder": [i.get("name") or "_" for i in inputs],
				}
			)

		return {
			"message": "Contract description ready.",
			"formattedSummary": _build_formatted_summary(contract, function_descriptions, len(functions)),
			"contract": {
				"contractName": contract.get("contractName") or "(Unnamed Contract)",
				"contractAddress": contract.get("contractAddress"),
				"networkName": contract.get("networkName"),
				"userAddress": contract.get("userAddress"),
				"functionsCount": len(functions),
				"shownFunctions": len(function_descriptions),
			},
			"note": "Arguments must be provided in strict positional order.",
			"functions": function_descriptions,
			"source": "local-registry",
		}
	except Exception as error:
		return {
			"error": f"describeContract error: {error}",
			"source": "local-registry",
		}
