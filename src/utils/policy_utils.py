"""Deterministic policy helpers for tool-level user knowledge enforcement."""

import json
from typing import Any

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from agents.BlockchainAgent.plugin.activity_logger_plugin import log_policy_check

from utils.prompts import DEFAULT_LEVEL, get_level_label, normalize_knowledge_level


KNOWLEDGE_LEVEL_STATE_KEY = "knowledge_level"
POLICY_CONFIRMATION_STATE_KEY = "_policy_pending_confirmations"

DEFI_TOOL_NAMES = {
  "stake",
  "deposit",
  "lend",
  "borrow",
  "repay",
  "withdraw",
  "approve",
  "claimRewards",
}

STATE_CHANGING_TOOL_NAMES = {
  "prepareTransaction",
  "interactWithContract",
  "stake",
  "deposit",
  "lend",
  "borrow",
  "repay",
  "withdraw",
  "approve",
  "claimRewards",
}


def _canonicalize(value: Any) -> Any:
  if value is None or isinstance(value, (str, int, float, bool)):
    return value
  if isinstance(value, dict):
    return {str(k): _canonicalize(v) for k, v in sorted(value.items())}
  if isinstance(value, (list, tuple, set)):
    return [_canonicalize(v) for v in value]
  return str(value)


def _tool_signature(agent_name: str | None, tool_name: str, tool_args: dict[str, Any]) -> str:
  payload = {
    "agent": agent_name or "",
    "tool": tool_name,
    "args": _canonicalize(tool_args),
  }
  return json.dumps(payload, sort_keys=True, ensure_ascii=True)


def _is_defi_tool(tool_name: str) -> bool:
  return tool_name in DEFI_TOOL_NAMES


def _is_state_changing_tool(tool_name: str) -> bool:
  return tool_name in STATE_CHANGING_TOOL_NAMES


def _extract_user_text(content: types.Content | None) -> str:
  if not content:
    return ""

  parts = getattr(content, "parts", None) or []
  chunks: list[str] = []
  for part in parts:
    text = getattr(part, "text", None)
    if text:
      chunks.append(str(text).strip())
  return "\n".join(chunks).strip()


def _normalize_yes_no(value: str) -> str | None:
  raw = (value or "").strip().lower()
  if not raw:
    return None

  # UI messages can include extra metadata after the user answer.
  # We accept explicit yes/no on the first non-empty line or as the first token.
  first_line = next((line.strip() for line in raw.splitlines() if line.strip()), "")
  first_token = first_line.split()[0] if first_line else ""
  first_token = first_token.strip(".,!?;:'\"`()[]{}")

  if first_line in {"yes", "y"} or first_token in {"yes", "y"}:
    return "yes"
  if first_line in {"no", "n"} or first_token in {"no", "n"}:
    return "no"
  return None


def _emit_policy_check_log(
  *,
  tool_context: ToolContext,
  tool_name: str,
  tool_args: dict[str, Any],
  knowledge_level: int,
  decision: str,
  reason: str,
) -> None:
  log_policy_check(
    {
      "request_id": tool_context.state.get("active_request_id"),
      "invocation_id": tool_context.invocation_id,
      "agent": tool_context.agent_name,
      "tool_name": tool_name,
      "tool_args": tool_args,
      "knowledgeLevel": knowledge_level,
      "knowledgeLevelLabel": get_level_label(knowledge_level),
      "callback": "check_user_level",
      "executed": True,
      "decision": decision,
      "reason": reason,
    }
  )


async def evaluate_user_level_tool_policy(
  tool: BaseTool,
  tool_args: dict[str, Any],
  tool_context: ToolContext,
  *,
  knowledge_level_state_key: str,
) -> dict[str, Any] | None:
  """Apply deterministic DeFi/state-changing policy and return override response when blocked."""
  state = tool_context.state

  try:
    knowledge_level = normalize_knowledge_level(
      state.get(knowledge_level_state_key, DEFAULT_LEVEL)
    )
  except ValueError:
    knowledge_level = DEFAULT_LEVEL

  tool_name = tool.name
  agent_name = tool_context.agent_name
  is_defi = _is_defi_tool(tool_name)
  is_state_changing = _is_state_changing_tool(tool_name)

  if knowledge_level == 1 and is_defi:
    _emit_policy_check_log(
      tool_context=tool_context,
      tool_name=tool_name,
      tool_args=tool_args,
      knowledge_level=knowledge_level,
      decision="blocked",
      reason="beginner_defi_forbidden",
    )
    return {
      "error": "POLICY_FORBIDDEN",
      "message": (
        "This DeFi action is blocked because your current knowledge level is Beginner. "
        "DeFi operations can involve smart-contract vulnerabilities, price volatility, "
        "liquidation risk, slippage, and permanent loss of funds if a transaction is "
        "signed with incorrect parameters. DeFi transactions are often irreversible once "
        "confirmed on-chain. If you still want to proceed, you can switch your knowledge "
        "level to Intermediate and then try again."
      ),
      "policy": {
        "knowledgeLevel": 1,
        "knowledgeLevelLabel": "Beginner",
        "tool": tool_name,
        "agent": agent_name,
        "reason": "defi_not_allowed_for_beginner",
      },
    }

  requires_confirmation = False
  if knowledge_level == 1 and is_state_changing:
    requires_confirmation = True
  elif knowledge_level == 2 and (is_state_changing or is_defi):
    requires_confirmation = True

  if not requires_confirmation:
    _emit_policy_check_log(
      tool_context=tool_context,
      tool_name=tool_name,
      tool_args=tool_args,
      knowledge_level=knowledge_level,
      decision="allowed",
      reason="no_confirmation_required",
    )
    return None

  confirmations = state.get(POLICY_CONFIRMATION_STATE_KEY)
  if not isinstance(confirmations, dict):
    confirmations = {}

  signature = _tool_signature(agent_name, tool_name, tool_args)
  user_choice = _normalize_yes_no(_extract_user_text(tool_context.user_content))
  tracked = confirmations.get(signature)

  if tracked is None:
    confirmations[signature] = {
      "status": "pending",
    }
    state[POLICY_CONFIRMATION_STATE_KEY] = confirmations
    _emit_policy_check_log(
      tool_context=tool_context,
      tool_name=tool_name,
      tool_args=tool_args,
      knowledge_level=knowledge_level,
      decision="confirmation_required",
      reason="first_confirmation_request",
    )
    return {
      "error": "POLICY_CONFIRMATION_REQUIRED",
      "message": (
        f"Before executing '{tool_name}', please confirm this action. "
        "This operation can be risky because blockchain transactions are permanent and "
        "can use funds from your wallet. Reply with exactly 'yes' to proceed or 'no' to cancel."
      ),
      "policy": {
        "knowledgeLevel": knowledge_level,
        "knowledgeLevelLabel": get_level_label(knowledge_level),
        "tool": tool_name,
        "agent": agent_name,
        "requiresExplicitConfirmation": True,
        "acceptedResponses": ["yes", "no"],
      },
    }

  if user_choice == "yes":
    confirmations.pop(signature, None)
    state[POLICY_CONFIRMATION_STATE_KEY] = confirmations
    _emit_policy_check_log(
      tool_context=tool_context,
      tool_name=tool_name,
      tool_args=tool_args,
      knowledge_level=knowledge_level,
      decision="allowed",
      reason="explicit_yes",
    )
    return None

  if user_choice == "no":
    confirmations.pop(signature, None)
    state[POLICY_CONFIRMATION_STATE_KEY] = confirmations
    _emit_policy_check_log(
      tool_context=tool_context,
      tool_name=tool_name,
      tool_args=tool_args,
      knowledge_level=knowledge_level,
      decision="cancelled",
      reason="explicit_no",
    )
    return {
      "error": "POLICY_ACTION_CANCELLED",
      "message": (
        f"Execution of '{tool_name}' has been cancelled as requested."
      ),
      "policy": {
        "knowledgeLevel": knowledge_level,
        "knowledgeLevelLabel": get_level_label(knowledge_level),
        "tool": tool_name,
        "agent": agent_name,
        "requiresExplicitConfirmation": True,
        "acceptedResponses": ["yes", "no"],
        "status": "cancelled",
      },
    }

  state[POLICY_CONFIRMATION_STATE_KEY] = confirmations
  _emit_policy_check_log(
    tool_context=tool_context,
    tool_name=tool_name,
    tool_args=tool_args,
    knowledge_level=knowledge_level,
    decision="confirmation_required",
    reason="pending_confirmation_invalid_or_missing_yes_no",
  )
  return {
    "error": "POLICY_CONFIRMATION_REQUIRED",
    "message": (
      f"I still need an explicit confirmation before executing '{tool_name}'. "
      "This operation can be risky because it is permanent on-chain and can use wallet funds. "
      "Please reply with exactly 'yes' to proceed or 'no' to cancel."
    ),
    "policy": {
      "knowledgeLevel": knowledge_level,
      "knowledgeLevelLabel": get_level_label(knowledge_level),
      "tool": tool_name,
      "agent": agent_name,
      "requiresExplicitConfirmation": True,
      "acceptedResponses": ["yes", "no"],
    },
  }


async def check_user_level(
  tool: BaseTool,
  args: dict[str, Any],
  tool_context: ToolContext,
) -> dict[str, Any] | None:
  """Shared before_tool_callback enforcing policy across root and subagents."""
  return await evaluate_user_level_tool_policy(
    tool,
    args,
    tool_context,
    knowledge_level_state_key=KNOWLEDGE_LEVEL_STATE_KEY,
  )