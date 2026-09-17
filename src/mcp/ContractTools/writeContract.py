import re
from datetime import datetime
from pathlib import Path

from litellm import acompletion
from utils.tool_utils import sanitize_name


SYSTEM_PROMPT = """
You are an expert blockchain developer specializing in writing secure and production-ready smart contracts.

STRICT CONSTRAINTS:
- Do NOT include import statements.
- Do NOT use external libraries or packages (including OpenZeppelin).
- If a common pattern is needed (Ownable, ReentrancyGuard, ERC-like behavior), implement a minimal inline version.

GENERAL RULES:
1) Default language is Solidity unless user explicitly asks for another language.
2) Include SPDX and pragma.
3) Return only contract code in a single ```solidity fenced block.
4) Keep code clean and concise.
""".strip()


def _extract_text_from_litellm_response(response) -> str:
	try:
		choices = getattr(response, "choices", None) or response.get("choices", [])
		if not choices:
			return ""
		message = choices[0].message if hasattr(choices[0], "message") else choices[0].get("message", {})
		content = getattr(message, "content", None) or message.get("content", "")
		return content or ""
	except Exception:
		return ""


def _extract_solidity(text: str) -> str:
	if not text:
		return ""

	patterns = [
		r"```solidity\n([\s\S]*?)```",
		r"```sol\n([\s\S]*?)```",
		r"```\n([\s\S]*?)```",
	]
	for pattern in patterns:
		match = re.search(pattern, text, re.IGNORECASE)
		if match and re.search(r"pragma\s+solidity", match.group(1), re.IGNORECASE):
			return match.group(1).strip()

	pragma_match = re.search(r"pragma\s+solidity[^;]*;", text, re.IGNORECASE)
	if pragma_match:
		return text[pragma_match.start():].strip()

	return ""


def _guess_contract_name(solidity_source: str) -> str:
	match = re.search(r"\bcontract\s+([A-Za-z_][A-Za-z0-9_]*)", solidity_source)
	return match.group(1) if match else "Contract"

async def writeContract(userMessage: str) -> dict:
	"""Generate a smart contract from user requirements and save it locally."""
	try:
		message = (userMessage or "").strip()
		if not message:
			return {
				"error": "No requirements found.",
				"source": "llm",
			}

		response = await acompletion(
			model="claude-sonnet-4-6",
			max_tokens=4096,
			messages=[
				{"role": "system", "content": SYSTEM_PROMPT},
				{"role": "user", "content": message},
			],
		)

		raw_output = _extract_text_from_litellm_response(response)
		solidity = _extract_solidity(raw_output)
		if not solidity or not re.search(r"pragma\s+solidity", solidity, re.IGNORECASE):
			return {
				"error": "The model did not return a valid Solidity contract.",
				"source": "llm",
			}

		contract_name = sanitize_name(_guess_contract_name(solidity))
		generated_dir = Path(__file__).resolve().parents[3] / ".generated-contracts"
		generated_dir.mkdir(parents=True, exist_ok=True)

		stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
		file_name = f"generated-{contract_name}-{stamp}.sol"
		file_path = generated_dir / file_name
		file_path.write_text(solidity, encoding="utf-8")

		return {
			"message": "Contract generated successfully.",
			"fileName": file_name,
			"filePath": str(file_path),
			"source": "llm",
			"disclaimer": "Review and audit the generated contract before deployment.",
		}
	except Exception as error:
		return {
			"error": f"Error during contract generation: {error}",
			"source": "llm",
		}
