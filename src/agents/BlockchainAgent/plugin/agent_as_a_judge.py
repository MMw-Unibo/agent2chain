# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Guardian plugin to run steward agents."""

import os
import enum
import logging
from collections.abc import Callable
from typing import Any

from google.adk.agents import invocation_context, llm_agent
from google.adk.events import event
from google.adk.models.lite_llm import LiteLlm
from google.adk.models import base_llm, llm_request, llm_response
from google.adk.models.registry import LLMRegistry
from google.adk.plugins import base_plugin
from google.adk.tools import base_tool, tool_context
from google.genai import types

from utils import prompts
from utils.system_utils import load_src_env

Event = event.Event
CallbackContext = base_plugin.CallbackContext
ToolContext = tool_context.ToolContext
InvocationContext = invocation_context.InvocationContext
LlmAgent = llm_agent.LlmAgent
BaseLlm = base_llm.BaseLlm
LlmRequest = llm_request.LlmRequest
BasePlugin = base_plugin.BasePlugin
LlmResponse = llm_response.LlmResponse
BaseTool = base_tool.BaseTool

load_src_env()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

_USER_PROMPT_REMOVED_MESSAGE = (
    "I cannot answer this question. I'm a blockchain agent and I can only answer" \
    " questions related to blockchain."
)
_UNSAFE_TOOL_INPUT_MESSAGE = "Unable to call tool due to unsafe inputs."
_UNSAFE_TOOL_OUTPUT_MESSAGE = (
    "Unable to emit tool result due to unsafe tool output."
)
_MODEL_RESPONSE_REMOVED_MESSAGE = (
    "A safety filter has removed the model's response as it was deemed unsafe."
)
_OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE") or "http://localhost:11434"
_OLLAMA_MAX_OUTPUT_TOKENS = 16
_OLLAMA_TEMPERATURE = 0.0
_RECENT_DIALOGUE_STATE_KEY = "recent_dialogue"
_MAX_DIALOGUE_ITEMS_FOR_JUDGE = 4
_MAX_DIALOGUE_TEXT_LENGTH_FOR_JUDGE = 220

default_jailbreak_safety_agent = LlmAgent(
    model="ollama/gemma4",
    name="jailbreak_safety_agent",
    instruction=prompts.JAILBREAK_FILTER_INSTRUCTION,
)

default_safety_analysis_parser = lambda analysis: "UNSAFE" in analysis


class JudgeOn(enum.StrEnum):
    """Enum for the different callbacks to run the judge on."""

    USER_MESSAGE = "user_message"
    BEFORE_TOOL_CALL = "before_tool_call"
    TOOL_OUTPUT = "tool_output"
    MODEL_OUTPUT = "model_output"


class LlmAsAJudge(BasePlugin):
    """A custom plugin that runs an LLM as a judge."""

    def __init__(
        self,
        judge_agent: LlmAgent = default_jailbreak_safety_agent,
        analysis_parser: Callable[[str], bool] = default_safety_analysis_parser,
        judge_on: set[str] | None = None,
    ) -> None:
        """Initialize the plugin.

        Args:
          judge_agent: The agent to use as the judge.
          judge_on: A list of callbacks to run the judge on. Can contain
            'user_message', 'before_tool_call', 'tool_output', 'model_output'.
            Defaults to ['user_message', 'tool_output'].
          analysis_parser: A function to parse the judge's analysis and return a
            boolean indicating if the message is unsafe or not. True indicates
            unsafe, False indicates safe.
        """
        super().__init__(name="judge_agent")

        self._judge_agent = judge_agent

        judge_model = self._judge_agent.model
        if isinstance(judge_model, str):
            model_id = judge_model
            self._judge_model_id = model_id
            self._is_ollama_model = model_id.startswith("ollama/") or model_id.startswith("ollama_chat/")
            if self._is_ollama_model:
                self._judge_llm = None
            else:
                llm_class = LLMRegistry().resolve(model_id)
                self._judge_llm = llm_class(model=model_id)
        else:
            self._judge_llm = judge_model
            self._judge_model_id = judge_model.model
            self._is_ollama_model = self._judge_model_id.startswith("ollama/") or self._judge_model_id.startswith("ollama_chat/")

        if judge_on is None:
            judge_on = {JudgeOn.USER_MESSAGE, JudgeOn.TOOL_OUTPUT}

        self._judge_on = judge_on
        self._analysis_parser = analysis_parser

    async def _is_unsafe(self, invocation_context: InvocationContext, message: str) -> bool:
        """Runs the LLM as a judge on the given message."""
        try:
            if self._is_ollama_model:
                from litellm import acompletion

                judge_instruction = ""
                if isinstance(self._judge_agent.instruction, str) and self._judge_agent.instruction.strip():
                    judge_instruction = self._judge_agent.instruction

                judge_response = await acompletion(
                    model=self._judge_model_id,
                    api_base=_OLLAMA_API_BASE,
                    messages=[
                        {"role": "system", "content": judge_instruction},
                        {"role": "user", "content": message},
                    ],
                    max_tokens=_OLLAMA_MAX_OUTPUT_TOKENS,
                    think=False,
                    temperature=_OLLAMA_TEMPERATURE,
                    extra_body={"guided_choice": ["<SAFE>", "<UNSAFE>"]},
                )

                choice = judge_response.choices[0] if getattr(judge_response, "choices", None) else None
                judge_analysis = ""
                if choice is not None:
                    judge_analysis = str(getattr(getattr(choice, "message", None), "content", "") or "").strip()

                is_unsafe = self._analysis_parser(judge_analysis)
                logging.debug(
                    "[%s]: `%s` (is_unsafe: %s)", self._judge_agent.name, judge_analysis, is_unsafe
                )
                return is_unsafe

            judge_analysis = ""
            judge_request = LlmRequest(
                model=self._judge_model_id,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=message)],
                    )
                ],
            )

            if isinstance(self._judge_agent.instruction, str) and self._judge_agent.instruction.strip():
                judge_request.config.system_instruction = self._judge_agent.instruction

            judge_request.config.max_output_tokens = 10

            async for judge_response in self._judge_llm.generate_content_async(judge_request):
                response_content = getattr(judge_response, "content", None)
                if not response_content:
                    continue
                parts = getattr(response_content, "parts", None) or []
                chunks = [getattr(part, "text", "") for part in parts if getattr(part, "text", "")]
                if chunks:
                    judge_analysis = "\n".join(chunks).strip()

            is_unsafe = self._analysis_parser(judge_analysis)
            logging.debug(
                "[%s]: `%s` (is_unsafe: %s)", self._judge_agent.name, judge_analysis, is_unsafe
            )
            return is_unsafe
        except Exception as judge_error:
            logging.exception("Judge plugin failed, allowing request to proceed: %s", judge_error)
            return False

    def _build_user_message_for_judge(
        self,
        invocation_context: InvocationContext,
        user_text: str,
    ) -> str:
        recent_dialogue = invocation_context.session.state.get(_RECENT_DIALOGUE_STATE_KEY, [])
        formatted_lines: list[str] = []

        if isinstance(recent_dialogue, list):
            for item in recent_dialogue[-_MAX_DIALOGUE_ITEMS_FOR_JUDGE:]:
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role", "")).strip().lower()
                if role not in {"user", "assistant"}:
                    continue
                text = " ".join(str(item.get("text", "")).split()).strip()
                if not text:
                    continue
                clipped = text[:_MAX_DIALOGUE_TEXT_LENGTH_FOR_JUDGE]
                formatted_lines.append(f"- {role}: {clipped}")

        normalized_user_text = " ".join(str(user_text or "").split()).strip()

        if not formatted_lines:
            return f"<user_message>\n{normalized_user_text}\n</user_message>"

        context_block = "\n".join(formatted_lines)
        return (
            "<user_message>\n"
            "Recent dialogue context (oldest to newest):\n"
            f"{context_block}\n\n"
            "Current user message:\n"
            f"{normalized_user_text}\n"
            "</user_message>"
        )

    async def on_user_message_callback(
        self,
        invocation_context: InvocationContext,
        user_message: types.Content,
    ) -> types.Content | None:
        if JudgeOn.USER_MESSAGE not in self._judge_on:
            return None
        user_text = ""
        if getattr(user_message, "parts", None):
            user_text = getattr(user_message.parts[0], "text", "") or ""

        message = self._build_user_message_for_judge(invocation_context, user_text)
        if await self._is_unsafe(invocation_context, message):
            invocation_context.session.state["is_user_prompt_safe"] = False
            return types.Content(
                role="user",
                parts=[types.Part.from_text(text=_USER_PROMPT_REMOVED_MESSAGE)],
            )

    async def before_run_callback(
        self,
        invocation_context: InvocationContext,
    ) -> types.Content | None:
        if not invocation_context.session.state.get(
            "is_user_prompt_safe", True
        ):
            invocation_context.session.state["is_user_prompt_safe"] = True
            return types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text=_USER_PROMPT_REMOVED_MESSAGE,
                    )
                ],
            )

    async def before_tool_callback(
        self,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
    ) -> dict[str, Any] | None:
        if JudgeOn.BEFORE_TOOL_CALL not in self._judge_on:
            return None
        message = (
            f"<tool_call>\nTool call: {tool.name}({tool_args!s})\n</tool_call>"
        )
        if await self._is_unsafe(tool_context._invocation_context, message):
            return {"error": _UNSAFE_TOOL_INPUT_MESSAGE}

    async def after_tool_callback(
        self,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        result: dict[str, Any],
    ) -> dict[str, Any] | None:
        if JudgeOn.TOOL_OUTPUT not in self._judge_on:
            return None
        message = f"<tool_output>\n{result!s}\n</tool_output>"
        if await self._is_unsafe(tool_context._invocation_context, message):
            return {"error": _UNSAFE_TOOL_OUTPUT_MESSAGE}

    async def after_model_callback(
        self,
        callback_context: CallbackContext,
        llm_response: LlmResponse,
    ) -> LlmResponse | None:
        if JudgeOn.MODEL_OUTPUT not in self._judge_on:
            return None
        llm_content = llm_response.content
        if not llm_content or not llm_content.parts:
            return None
        model_output = "\n".join(
            [part.text or "" for part in llm_content.parts]
        ).strip()
        if not model_output:
            return None
        message = f"<model_output>\n{model_output}\n</model_output>"
        if await self._is_unsafe(callback_context._invocation_context, message):
            return types.Content(
                role="model",
                parts=[
                    types.Part.from_text(text=_MODEL_RESPONSE_REMOVED_MESSAGE)
                ],
            )