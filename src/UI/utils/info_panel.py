"""Helpers to build concise Info Panel events from activity logs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.BlockchainAgent.plugin.activity_logger_plugin import get_log_dir

_ACTIVITY_LOG_FILE = "agent_activity.jsonl"
_MAX_EVENTS_PER_REQUEST = 30
_MAX_INLINE_VALUE_LEN = 80


_ALLOWED_EVENT_TYPES = {
    "transfer_to_agent",
    "tool_invocation",
    "tool_response",
    "agent_response",
    "request_error",
    "policy_check",
}


def _truncate(text: str, max_len: int = _MAX_INLINE_VALUE_LEN) -> str:
    compact = " ".join(str(text or "").split()).strip()
    if len(compact) <= max_len:
        return compact
    return f"{compact[: max_len - 3]}..."


def _short_hex(value: str) -> str:
    text = str(value or "")
    if text.startswith("0x") and len(text) >= 16:
        return f"{text[:8]}...{text[-6:]}"
    return text


def _compact_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return _truncate(_short_hex(value))
    if isinstance(value, list):
        return f"[{len(value)} items]"
    if isinstance(value, dict):
        return f"{{{len(value)} keys}}"
    return _truncate(str(value))


def _summarize_args(tool_args: Any) -> str:
    if not isinstance(tool_args, dict) or not tool_args:
        return "no params"

    chunks: list[str] = []
    for key in sorted(tool_args.keys())[:5]:
        chunks.append(f"{key}={_compact_value(tool_args.get(key))}")
    suffix = "" if len(tool_args) <= 5 else ", ..."
    return ", ".join(chunks) + suffix


def _extract_result_summary(result: Any) -> tuple[str, str | None]:
    if isinstance(result, dict):
        for key in ("error", "message"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                kind = "error" if key == "error" else "ok"
                return kind, _truncate(value, max_len=140)

        tx_data = result.get("transactionData")
        if isinstance(tx_data, dict):
            tx_hash = tx_data.get("hash") or tx_data.get("txHash") or tx_data.get("transactionHash")
            if tx_hash:
                return "ok", f"tx={_short_hex(str(tx_hash))}"

        for key in ("contractAddress", "address", "txHash", "transactionHash", "hash"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return "ok", f"{key}={_short_hex(value)}"

        keys = sorted(str(key) for key in result.keys())
        if keys:
            preview = ", ".join(keys[:5])
            if len(keys) > 5:
                preview += ", ..."
            return "ok", f"result keys: {preview}"

    if isinstance(result, str) and result.strip():
        return "ok", _truncate(result, max_len=140)

    return "ok", None


def _policy_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    decision = str(payload.get("decision") or "").strip().lower()
    if decision in {"allowed", ""}:
        return None

    tool_name = str(payload.get("tool_name") or "tool")
    agent_name = str(payload.get("agent") or "unknown")
    reason = str(payload.get("reason") or "policy decision")

    return {
        "type": "policy_check",
        "level": "warn" if decision == "confirmation_required" else "error",
        "headline": f"Policy {decision}: {tool_name}",
        "details": f"agent={agent_name} | reason={_truncate(reason)}",
    }


def _summarize_event(record: dict[str, Any]) -> dict[str, Any] | None:
    event_type = str(record.get("event_type") or "")
    if event_type not in _ALLOWED_EVENT_TYPES:
        return None

    payload = record.get("payload")
    if not isinstance(payload, dict):
        return None

    timestamp = str(record.get("timestamp") or "")

    if event_type == "transfer_to_agent":
        from_agent = str(payload.get("from_agent") or "unknown")
        to_agent = str(payload.get("to_agent") or "unknown")
        return {
            "type": event_type,
            "level": "info",
            "timestamp": timestamp,
            "headline": f"Transfer: {from_agent} -> {to_agent}",
            "details": None,
        }

    if event_type == "tool_invocation":
        tool_name = str(payload.get("tool_name") or "unknown_tool")
        agent_name = str(payload.get("agent") or "unknown")
        arg_text = _summarize_args(payload.get("tool_args"))
        return {
            "type": event_type,
            "level": "info",
            "timestamp": timestamp,
            "headline": f"Tool request: {tool_name}",
            "details": f"agent={agent_name} | {arg_text}",
        }

    if event_type == "tool_response":
        tool_name = str(payload.get("tool_name") or "unknown_tool")
        agent_name = str(payload.get("agent") or "unknown")
        status, summary = _extract_result_summary(payload.get("result"))
        return {
            "type": event_type,
            "level": "error" if status == "error" else "ok",
            "timestamp": timestamp,
            "headline": f"Tool response: {tool_name}",
            "details": (
                f"agent={agent_name}"
                if not summary
                else f"agent={agent_name} | {summary}"
            ),
        }

    if event_type == "agent_response":
        agent_name = str(payload.get("agent") or "unknown")
        response_text = str(payload.get("response") or "").strip()
        details = f"agent={agent_name}"
        if response_text:
            details = f"agent={agent_name} | {_truncate(response_text, max_len=180)}"
        else:
            details = f"agent={agent_name} | (empty response)"
        return {
            "type": event_type,
            "level": "info",
            "timestamp": timestamp,
            "headline": "Agent response",
            "details": details,
        }

    if event_type == "request_error":
        message = str(payload.get("detailed_error") or payload.get("error") or "Unknown request error")
        return {
            "type": event_type,
            "level": "error",
            "timestamp": timestamp,
            "headline": "Request error",
            "details": _truncate(message, max_len=180),
        }

    if event_type == "policy_check":
        policy_event = _policy_summary(payload)
        if not policy_event:
            return None
        policy_event["timestamp"] = timestamp
        return policy_event

    return None


def _iter_log_lines(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return handle.readlines()
    except OSError:
        return []


def build_request_info_events(
    request_id: str,
    *,
    invocation_id: str | None = None,
    max_events: int = _MAX_EVENTS_PER_REQUEST,
) -> list[dict[str, Any]]:
    """Return concise, request-scoped events for the UI Info Panel."""
    request_id = str(request_id or "").strip()
    invocation_id = str(invocation_id or "").strip()
    if not request_id and not invocation_id:
        return []

    log_path = get_log_dir() / _ACTIVITY_LOG_FILE
    if not log_path.exists():
        return []

    events: list[dict[str, Any]] = []
    for raw_line in _iter_log_lines(log_path):
        line = raw_line.strip()
        if not line:
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue

        payload_request_id = str(payload.get("request_id") or "").strip()
        payload_invocation_id = str(payload.get("invocation_id") or "").strip()

        matched = False
        if request_id and payload_request_id == request_id:
            matched = True
        if invocation_id and payload_invocation_id == invocation_id:
            matched = True

        if not matched:
            continue

        summary = _summarize_event(record)
        if summary is None:
            continue
        events.append(summary)

    if max_events > 0 and len(events) > max_events:
        return events[-max_events:]
    return events
