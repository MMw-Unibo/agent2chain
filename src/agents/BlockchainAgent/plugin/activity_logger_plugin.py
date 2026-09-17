"""ADK callback-based activity logging plugin."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any

from google.adk.agents.base_agent import BaseAgent
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin, CallbackContext
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

_LOG_LOCK = Lock()
_DEFAULT_LOG_FILE = "agent_activity.jsonl"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def get_log_dir() -> Path:
    configured = os.getenv("BLOCKCHAIN_AGENT_LOG_DIR", "").strip()
    log_dir = Path(configured) if configured else (_project_root() / ".logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _safe(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return str(value)

    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {str(k): _safe(v, depth + 1) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_safe(item, depth + 1) for item in value]

    if hasattr(value, "model_dump"):
        try:
            return _safe(value.model_dump(mode="json"), depth + 1)
        except Exception:
            pass

    if hasattr(value, "dict"):
        try:
            return _safe(value.dict(), depth + 1)
        except Exception:
            pass

    return str(value)


def log_activity(event_type: str, payload: dict[str, Any], log_file: str = _DEFAULT_LOG_FILE) -> None:
    """Append one structured activity event into project-root .logs/<log_file> in JSONL format."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "payload": _safe(payload),
    }

    target_file = get_log_dir() / log_file
    serialized = json.dumps(record, ensure_ascii=True)

    with _LOG_LOCK:
        with target_file.open("a", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.write("\n")


def log_policy_check(payload: dict[str, Any]) -> None:
    """Append one policy callback evaluation event to the activity log.

    This helper is intentionally safe: logging failures must never break runtime policy checks.
    """
    try:
        log_activity("policy_check", payload)
    except Exception:
        return


class ActivityLoggerPlugin(BasePlugin):
    """Passive ADK plugin that emits structured JSONL activity records."""

    _STATE_LAST_AGENT_KEY = "_activity_logger_last_agent"

    def __init__(self) -> None:
        super().__init__(name="activity_logger")

    @staticmethod
    def _safe_log(event_type: str, payload: dict[str, Any]) -> None:
        try:
            log_activity(event_type, payload)
        except Exception:
            # Logging must never interfere with the agent lifecycle.
            return

    @staticmethod
    def _extract_text_from_content(content: Any) -> str:
        if not content:
            return ""

        parts = getattr(content, "parts", None) or []
        chunks: list[str] = []
        for part in parts:
            text = getattr(part, "text", None)
            if text:
                chunks.append(str(text))
        return "\n".join(chunks).strip()

    @staticmethod
    def _request_id_from_state(state: dict[str, Any]) -> str | None:
        value = state.get("active_request_id")
        if value is None:
            return None
        return str(value)

    async def on_user_message_callback(
        self,
        *,
        invocation_context,
        user_message: types.Content,
    ) -> types.Content | None:
        user_text = self._extract_text_from_content(user_message)
        request_id = self._request_id_from_state(invocation_context.session.state)
        self._safe_log(
            "user_message",
            {
                "request_id": request_id,
                "invocation_id": invocation_context.invocation_id,
                "user_id": invocation_context.user_id,
                "session_id": invocation_context.session.id,
                "message": user_text,
            },
        )
        return None

    async def before_agent_callback(
        self,
        *,
        agent: BaseAgent,
        callback_context: CallbackContext,
    ) -> types.Content | None:
        state = callback_context.state
        current_agent = callback_context.agent_name or getattr(agent, "name", None)
        previous_agent = state.get(self._STATE_LAST_AGENT_KEY)
        request_id = self._request_id_from_state(state)

        if previous_agent and current_agent and previous_agent != current_agent:
            self._safe_log(
                "transfer_to_agent",
                {
                    "request_id": request_id,
                    "invocation_id": callback_context.invocation_id,
                    "from_agent": str(previous_agent),
                    "to_agent": str(current_agent),
                },
            )

        if current_agent:
            state[self._STATE_LAST_AGENT_KEY] = str(current_agent)
        return None

    async def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
    ) -> dict[str, Any] | None:
        request_id = self._request_id_from_state(tool_context.state)
        self._safe_log(
            "tool_invocation",
            {
                "request_id": request_id,
                "invocation_id": tool_context.invocation_id,
                "agent": tool_context.agent_name,
                "tool_name": tool.name,
                "tool_args": tool_args,
            },
        )
        return None

    async def after_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        result: dict[str, Any],
    ) -> dict[str, Any] | None:
        request_id = self._request_id_from_state(tool_context.state)
        self._safe_log(
            "tool_response",
            {
                "request_id": request_id,
                "invocation_id": tool_context.invocation_id,
                "agent": tool_context.agent_name,
                "tool_name": tool.name,
                "tool_args": tool_args,
                "result": result,
            },
        )
        return None

    async def after_model_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_response: LlmResponse,
    ) -> LlmResponse | None:
        request_id = self._request_id_from_state(callback_context.state)
        response_text = self._extract_text_from_content(getattr(llm_response, "content", None))
        self._safe_log(
            "agent_response",
            {
                "request_id": request_id,
                "invocation_id": callback_context.invocation_id,
                "agent": callback_context.agent_name,
                "response": response_text,
            },
        )
        return None