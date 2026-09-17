"""Utility functions for the Agent2Chain UI server."""

from __future__ import annotations

import importlib.util
import json
import os
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from UI.utils.knowledge_level_state import (
    DEFAULT_LEVEL,
    KNOWLEDGE_LEVEL_STATE_KEY,
    append_knowledge_level_marker,
    extract_knowledge_level,
    normalize_level,
)

from agents.BlockchainAgent.plugin.activity_logger_plugin import log_activity
from utils.message_utils import build_user_content, extract_text_from_event, format_agent_reply
from utils.prompts import (
    apply_blockchain_prompt_state_to_agent,
    change_chain_id,
    change_current_balance,
    change_current_level,
    change_current_network,
    change_user_account,
    DEFAULT_LEVEL,
    get_current_level,
    reset_blockchain_prompt_state,
)
from utils.supported_chains import resolve_chain

RECENT_DIALOGUE_STATE_KEY = "recent_dialogue"
MAX_RECENT_DIALOGUE_MESSAGES = 8
MAX_DIALOGUE_TEXT_LENGTH = 500


@lru_cache(maxsize=1)
def _load_scan_contract_tool():
    """Load local scanContract tool by file path, avoiding `mcp` package name collisions."""
    tool_path = Path(__file__).resolve().parents[2] / "mcp" / "ContractTools" / "scanContract.py"
    spec = importlib.util.spec_from_file_location("adk_scan_contract_tool", tool_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load scanContract tool module at {tool_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    scan_contract = getattr(module, "scanContract", None)
    if scan_contract is None:
        raise ImportError("scanContract function not found in scanContract.py")
    return scan_contract


def load_src_env(src_dir: Path) -> None:
    """Load src/.env so custom launches still get API keys."""
    env_path = src_dir / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue

        if value:
            os.environ[key] = value
        else:
            os.environ.setdefault(key, value)


def normalize_ui_get_path(path: str) -> str:
    """Normalize legacy UI paths to current static file paths."""
    if path in {"/", "/index.html", "/UI", "/UI/"}:
        return "/index.html"

    if not path.startswith("/UI/"):
        return path

    legacy_path = path.removeprefix("/UI")
    if legacy_path in {"/", "/ai_agent.html"}:
        return "/index.html"
    if legacy_path == "/styles.css":
        return "/styles.css"
    if legacy_path == "/interact.js":
        return "/app.js"
    return legacy_path


def read_json_request_body(handler: Any) -> dict[str, Any]:
    """Read and parse a JSON HTTP request body."""
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw_body = handler.rfile.read(content_length).decode("utf-8")
    return json.loads(raw_body) if raw_body else {}


def _extract_metamask_payloads(value: Any) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []

    if isinstance(value, dict):
        action = value.get("clientAction")
        tx_data = value.get("transactionData")
        if action == "metamask_send_transaction" and isinstance(tx_data, dict):
            payloads.append(
                {
                    "clientAction": action,
                    "transactionData": tx_data,
                    "message": str(value.get("message", "")).strip(),
                }
            )

        for nested in value.values():
            payloads.extend(_extract_metamask_payloads(nested))
        return payloads

    if isinstance(value, list):
        for item in value:
            payloads.extend(_extract_metamask_payloads(item))
        return payloads

    if isinstance(value, str):
        candidate = value.strip()
        if candidate.startswith("{") and candidate.endswith("}"):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                return payloads
            payloads.extend(_extract_metamask_payloads(parsed))

    return payloads


def _compact_dialogue_text(text: str) -> str:
    return " ".join(str(text or "").split()).strip()[:MAX_DIALOGUE_TEXT_LENGTH]


def _append_recent_dialogue(state: dict[str, Any], role: str, text: str) -> None:
    if role not in {"user", "assistant"}:
        return

    compact_text = _compact_dialogue_text(text)
    if not compact_text:
        return

    current = state.get(RECENT_DIALOGUE_STATE_KEY)
    if not isinstance(current, list):
        current = []

    current.append({"role": role, "text": compact_text})
    state[RECENT_DIALOGUE_STATE_KEY] = current[-MAX_RECENT_DIALOGUE_MESSAGES:]


def _extract_event_agent_name(event: Any) -> str:
    for attr in ("author", "agent_name", "agent"):
        value = getattr(event, attr, None)
        if value:
            return str(value)
    return ""


async def run_agent_request(
    user_message: str,
    wallet: dict[str, Any] | None,
    request_id: str,
    *,
    runner: Any,
    ensure_session: Any,
    user_id: str,
    session_id: str,
) -> dict[str, Any]:
    """Run one ADK request and serialize final response and invocation metadata for UI."""
    session = await ensure_session(user_id=user_id, session_id=session_id)

    saved_level = normalize_level(session.state.get(KNOWLEDGE_LEVEL_STATE_KEY))
    session.state[KNOWLEDGE_LEVEL_STATE_KEY] = saved_level
    change_current_level(saved_level)
    apply_blockchain_prompt_state_to_agent(runner.agent)

    content = build_user_content(user_message, wallet)

    final_chunks: list[str] = []
    fallback_chunks: list[str] = []
    metamask_payloads: list[dict[str, Any]] = []
    knowledge_level_updates: list[int] = []
    active_invocation_id: str | None = None

    session.state["active_request_id"] = request_id
    session.state.pop("_activity_logger_last_agent", None)

    async def _consume_events() -> None:
        nonlocal active_invocation_id
        last_agent_name = ""

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            event_invocation_id = getattr(event, "invocation_id", None)
            if active_invocation_id is None and event_invocation_id:
                active_invocation_id = str(event_invocation_id)

            event_agent = _extract_event_agent_name(event)
            if event_agent and event_agent != last_agent_name:
                last_agent_name = event_agent

            function_responses: list[dict[str, Any]] = []
            content_obj = getattr(event, "content", None)
            parts = getattr(content_obj, "parts", None) or []
            for part in parts:
                function_response = getattr(part, "function_response", None)
                if not function_response:
                    continue

                response_name = str(getattr(function_response, "name", "") or "")
                response_payload = getattr(function_response, "response", None)

                function_responses.append(
                    {
                        "name": response_name,
                        "response": response_payload,
                    }
                )

            for response_entry in function_responses:
                metamask_payloads.extend(_extract_metamask_payloads(response_entry))
                extracted_level = extract_knowledge_level(response_entry)
                if extracted_level is not None:
                    knowledge_level_updates.append(extracted_level)

            text = extract_text_from_event(event)
            if text:
                fallback_chunks.append(text)
            if hasattr(event, "is_final_response") and event.is_final_response() and text:
                final_chunks.append(text)

    try:
        await _consume_events()
    finally:
        session.state.pop("active_request_id", None)
        session.state.pop("_activity_logger_last_agent", None)

    if final_chunks:
        reply = format_agent_reply("\n".join(final_chunks))
    elif fallback_chunks:
        reply = format_agent_reply(fallback_chunks[-1])
    else:
        reply = format_agent_reply("I could not generate a response for this request.")

    reply_for_history = reply

    if metamask_payloads:
        serialized_payloads = {
            json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
            for payload in metamask_payloads
        }
        markers = "\n".join(
            f"__METAMASK_TX__{serialized}" for serialized in sorted(serialized_payloads)
        )
        reply = f"{reply}\n{markers}" if reply else markers

    if knowledge_level_updates:
        latest_level = knowledge_level_updates[-1]
        reply = append_knowledge_level_marker(reply, latest_level)

    _append_recent_dialogue(session.state, "user", user_message)
    _append_recent_dialogue(session.state, "assistant", reply_for_history)

    return {
        "reply": reply,
        "invocationId": active_invocation_id,
    }


def update_wallet_prompt_state(wallet: dict[str, Any], root_agent: Any) -> None:
    """Sync connected wallet state into root-agent prompt context."""
    connected = bool(wallet.get("connected", False))

    if not connected:
        current_level = normalize_level(get_current_level())
        reset_blockchain_prompt_state()
        change_current_level(current_level)
        apply_blockchain_prompt_state_to_agent(root_agent)
        return

    account = wallet.get("account")
    network_name = wallet.get("networkName")
    chain_id = wallet.get("chainId")
    balance_eth = wallet.get("balanceEth")

    if isinstance(account, str) and account.strip():
        change_user_account(account.strip())
    if isinstance(network_name, str) and network_name.strip():
        change_current_network(network_name.strip())
    if isinstance(chain_id, int):
        change_chain_id(chain_id)
    if isinstance(balance_eth, str) and balance_eth.strip():
        change_current_balance(f"{balance_eth.strip()} ETH")

    apply_blockchain_prompt_state_to_agent(root_agent)


def compile_contract_for_deploy(
    file_name: str,
    source: str,
    requested_contract_name: str | None,
    network_name: str | None,
) -> dict[str, Any]:
    """Compile Solidity source and return deployment payload for UI MetaMask flow."""
    try:
        from solcx import (
            compile_standard,
            get_installable_solc_versions,
            get_installed_solc_versions,
            install_solc,
            set_solc_version,
        )
    except Exception as import_error:
        raise RuntimeError(
            "Solidity compiler dependency missing. Install `py-solc-x` in this environment."
        ) from import_error

    configured_version = os.getenv("SOLC_VERSION", "").strip()
    if configured_version:
        solc_version = configured_version
    else:
        installable_versions = [str(version) for version in get_installable_solc_versions()]
        if not installable_versions:
            raise RuntimeError("No installable Solidity compiler versions found.")
        solc_version = installable_versions[0]

    installed = {str(version) for version in get_installed_solc_versions()}
    if solc_version not in installed:
        install_solc(solc_version)
    set_solc_version(solc_version)

    compiler_input = {
        "language": "Solidity",
        "sources": {file_name: {"content": source}},
        "settings": {
            "evmVersion": "paris",
            "optimizer": {"enabled": True, "runs": 200},
            "outputSelection": {"*": {"*": ["abi", "evm.bytecode.object"]}},
        },
    }

    output = compile_standard(compiler_input)
    errors = output.get("errors") or []
    fatal_errors = [
        issue.get("formattedMessage") or issue.get("message") or "Unknown compile error"
        for issue in errors
        if issue.get("severity") == "error"
    ]
    if fatal_errors:
        raise ValueError("\n".join(fatal_errors))

    contracts_by_file = output.get("contracts", {}).get(file_name, {})
    if not contracts_by_file:
        raise ValueError("No contracts found in source file.")

    contract_name = requested_contract_name if requested_contract_name in contracts_by_file else None
    if not contract_name:
        contract_name = next(iter(contracts_by_file.keys()))

    compiled = contracts_by_file.get(contract_name) or {}
    abi = compiled.get("abi")
    bytecode = (compiled.get("evm", {}).get("bytecode", {}).get("object") or "").strip()

    if not abi or not isinstance(abi, list):
        raise ValueError(f"Compiled ABI not found for contract '{contract_name}'.")
    if not bytecode:
        raise ValueError(f"Compiled bytecode not found for contract '{contract_name}'.")

    normalized_network = str(network_name or "").strip()
    chain_id = None
    if normalized_network:
        _, chain_data = resolve_chain(normalized_network)
        if chain_data:
            chain_id = chain_data.get("chainId")

    message = (
        f"Contract {contract_name} compiled successfully with solc {solc_version}. "
        "MetaMask will now ask for deployment confirmation."
    )

    return {
        "message": message,
        "deployData": {
            "fileName": file_name,
            "contractName": contract_name,
            "abi": abi,
            "bytecode": bytecode,
            "networkName": normalized_network or None,
            "chainId": chain_id,
            "compilerVersion": solc_version,
        },
    }


async def run_contract_scan(file_name: str, source: str, contract_name: str | None) -> dict[str, Any]:
    """Run smart contract vulnerability scan through ContractTools scanContract."""
    scan_contract = _load_scan_contract_tool()
    result = await scan_contract(contractName=contract_name, source=source)
    if not isinstance(result, dict):
        return {"error": "Unexpected scan result format."}

    if result.get("error"):
        return {
            "error": str(result.get("error")),
            "source": str(result.get("source") or "chaingpt"),
        }

    safe_contract_name = str(contract_name or "Contract").strip() or "Contract"
    report_name = str(result.get("reportFileName") or "")
    report_url = str(result.get("reportRelativeUrl") or "").strip()
    summary = str(result.get("summary") or "No findings summary available.")
    disclaimer = str(result.get("disclaimer") or "")

    markdown_lines = [
        f"### Vulnerability scan for `{safe_contract_name}`",
        "",
        "**Summary (preview):**",
        "```",
        summary,
        "```",
    ]

    if report_name and report_url:
        markdown_lines.extend([
            "",
            f"Detailed report: [{report_name}]({report_url})",
        ])

    if disclaimer:
        markdown_lines.extend(["", f"_Note: {disclaimer}_"])

    return {
        "message": str(result.get("message") or "Vulnerability scan completed."),
        "summary": summary,
        "reportFileName": report_name,
        "reportRelativeUrl": report_url,
        "source": str(result.get("source") or "chaingpt"),
        "disclaimer": disclaimer,
        "markdown": "\n".join(markdown_lines),
        "fileName": file_name,
    }


def _contracts_registry_path(src_dir: Path) -> Path:
    data_dir = src_dir.parent / ".data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "contracts.storage.json"


def _load_contract_registry(src_dir: Path) -> list[dict[str, Any]]:
    path = _contracts_registry_path(src_dir)
    if not path.exists():
        return []

    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _save_contract_registry(src_dir: Path, records: list[dict[str, Any]]) -> None:
    path = _contracts_registry_path(src_dir)
    path.write_text(json.dumps(records, indent=2, ensure_ascii=True), encoding="utf-8")


def register_deployed_contract(body: dict[str, Any], src_dir: Path) -> dict[str, Any]:
    """Store one deployed contract record inside .data/contracts.storage.json."""
    contract_address = str(body.get("contractAddress", "")).strip()
    if not contract_address:
        raise ValueError("contractAddress is required")

    record = {
        "contractName": str(body.get("contractName", "")).strip() or "(Unnamed Contract)",
        "contractAddress": contract_address,
        "networkName": str(body.get("networkName", "")).strip() or "unknown",
        "deployTxHash": str(body.get("deployTxHash", "")).strip() or None,
        "userAddress": str(body.get("userAddress", "")).strip() or "unknown",
        "fileName": str(body.get("fileName", "")).strip() or None,
        "constructorArgs": body.get("constructorArgs") if isinstance(body.get("constructorArgs"), list) else [],
        "abi": body.get("abi") if isinstance(body.get("abi"), list) else [],
        "bytecode": str(body.get("bytecode", "")).strip() or None,
        "savedAt": datetime.now(timezone.utc).isoformat(),
    }

    records = _load_contract_registry(src_dir)
    lookup_address = contract_address.lower()
    lookup_network = str(record["networkName"]).lower()
    lookup_user = str(record["userAddress"]).lower()

    updated = False
    for index, existing in enumerate(records):
        existing_address = str(existing.get("contractAddress", "")).strip().lower()
        existing_network = str(existing.get("networkName", "")).strip().lower()
        existing_user = str(existing.get("userAddress", "")).strip().lower()
        if (
            existing_address == lookup_address
            and existing_network == lookup_network
            and existing_user == lookup_user
        ):
            records[index] = {**existing, **record}
            updated = True
            break

    if not updated:
        records.append(record)

    _save_contract_registry(src_dir, records)

    log_activity(
        "deployed_contract_registered",
        {
            "contractAddress": record["contractAddress"],
            "contractName": record["contractName"],
            "networkName": record["networkName"],
            "userAddress": record["userAddress"],
        },
    )

    return {"ok": True, "saved": True}
