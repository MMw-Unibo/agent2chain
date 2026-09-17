import importlib
import os
from datetime import datetime
from pathlib import Path

from utils.tool_utils import sanitize_name


REQUEST_TIMEOUT_SECONDS = 120
STREAM_TIMEOUT_SECONDS = 300


def _build_audit_prompt(contract_name: str, source: str) -> str:
	return (
		f"Audit the following Solidity smart contract named '{contract_name}'.\n"
		"Identify vulnerabilities by severity (High/Medium/Low/Info), explain each finding, "
		"and provide remediation steps. Also include best-practice improvements.\n\n"
		f"```solidity\n{source}\n```"
	)


def _short_report(raw_text: str, max_lines: int = 20) -> str:
	lines = [line for line in str(raw_text).replace("\r\n", "\n").split("\n") if line.strip()]
	return "\n".join(lines[:max_lines]) + ("\n..." if len(lines) > max_lines else "")


async def scanContract(contractName: str | None = None, source: str | None = None) -> dict:
	"""Scan a Solidity smart contract for vulnerabilities using ChainGPT Python SDK."""
	try:
		if not source or not isinstance(source, str):
			return {
				"error": "Missing or invalid source code.",
				"source": "chaingpt",
			}

		api_key = os.getenv("CHAINGPT_API_KEY")
		if not api_key:
			return {
				"error": "Missing ChainGPT API key (CHAINGPT_API_KEY).",
				"source": "chaingpt",
			}

		try:
			client_module = importlib.import_module("chaingpt.client")
			auditor_models_module = importlib.import_module("chaingpt.models.auditor")
			types_module = importlib.import_module("chaingpt.types")
			exceptions_module = importlib.import_module("chaingpt.exceptions")

			ChainGPTClient = getattr(client_module, "ChainGPTClient")
			SmartContractAuditRequestModel = getattr(auditor_models_module, "SmartContractAuditRequestModel")
			ChatHistoryMode = getattr(types_module, "ChatHistoryMode")

			APIError = getattr(exceptions_module, "APIError")
			AuthenticationError = getattr(exceptions_module, "AuthenticationError")
			ChainGPTError = getattr(exceptions_module, "ChainGPTError")
			RateLimitError = getattr(exceptions_module, "RateLimitError")
			ChainGPTTimeoutError = getattr(exceptions_module, "TimeoutError")
			ValidationError = getattr(exceptions_module, "ValidationError")
		except Exception:
			return {
				"error": "ChainGPT SDK not installed. Install dependency `chaingpt` in this environment.",
				"source": "chaingpt",
			}

		safe_name = sanitize_name(contractName)
		question = _build_audit_prompt(safe_name, source)

		try:
			request = SmartContractAuditRequestModel(
				question=question,
				chatHistory=ChatHistoryMode.OFF,
			)

			async with ChainGPTClient(
				api_key=api_key,
				base_url="https://api.chaingpt.org",
				timeout=float(REQUEST_TIMEOUT_SECONDS),
				stream_timeout=float(STREAM_TIMEOUT_SECONDS),
			) as client:
				response = await client.auditor.audit_contract(request)
		except AuthenticationError:
			return {
				"error": "Invalid ChainGPT API key.",
				"source": "chaingpt",
			}
		except ValidationError as validation_error:
			return {
				"error": f"Invalid ChainGPT audit request: {validation_error}",
				"source": "chaingpt",
			}
		except RateLimitError as rate_error:
			return {
				"error": f"ChainGPT rate limit exceeded: {rate_error}",
				"source": "chaingpt",
			}
		except ChainGPTTimeoutError:
			return {
				"error": "ChainGPT request timed out.",
				"source": "chaingpt",
			}
		except APIError as api_error:
			return {
				"error": f"ChainGPT API error: {api_error}",
				"source": "chaingpt",
			}
		except ChainGPTError as sdk_error:
			return {
				"error": f"ChainGPT SDK error: {sdk_error}",
				"source": "chaingpt",
			}

		status = bool(getattr(response, "status", True))
		message = str(getattr(response, "message", "")).strip()
		report = str(getattr(getattr(response, "data", None), "bot", "") or "").strip()

		if not report:
			return {
				"error": message or "ChainGPT returned an empty audit report.",
				"source": "chaingpt",
			}
		if not status and message:
			# Keep report for visibility, but surface the warning in message.
			message = f"Audit completed with warnings: {message}"
		elif not message:
			message = f"Vulnerability scan completed for {safe_name}."

		summary = _short_report(report)

		project_root = Path(__file__).resolve().parents[3]
		reports_dir = project_root / ".reports"
		reports_dir.mkdir(parents=True, exist_ok=True)
		stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
		report_filename = f"api-scan-report-{safe_name}-{stamp}.txt"
		report_path = reports_dir / report_filename
		report_path.write_text(report, encoding="utf-8")

		return {
			"message": message,
			"summary": summary,
			"reportFileName": report_filename,
			"reportFilePath": str(report_path),
			"reportRelativeUrl": f"/reports/{report_filename}",
			"source": "chaingpt",
			"disclaimer": "Always review findings manually and run an independent security audit before deployment.",
		}
	except Exception as error:
		return {
			"error": f"scanContract error: {error}",
			"source": "chaingpt",
		}
