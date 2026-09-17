'''
    Agent for autonomously interacting with blockchain environments.
'''

import asyncio
import inspect
import os

from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from utils.policy_utils import check_user_level
from utils.prompts import (
  BLOCKCHAIN_AGENT_INSTRUCTION,
  apply_blockchain_prompt_state_to_agent,
  change_current_level,
  DEFAULT_LEVEL,
  get_level_label,
  normalize_knowledge_level,
)
from utils.system_utils import load_src_env
from .plugin import ActivityLoggerPlugin, LlmAsAJudge


load_src_env()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

from .subagents.info_agent.agent import info_agent, blockchain_info_mcp_toolset
from .subagents.metamask_agent.agent import metamask_agent, metamask_mcp_toolset
from .subagents.contract_agent.agent import contract_agent, contract_mcp_toolset
from .subagents.defi_agent.agent import defi_agent, defi_mcp_toolset

session_service = InMemorySessionService()
artifact_service = InMemoryArtifactService()

APP_NAME = "Agent4Blockchain"
USER_ID = "user_1"
SESSION_ID = "session_001"
KNOWLEDGE_LEVEL_STATE_KEY = "knowledge_level"


def setLevel(level: int | str, tool_context: ToolContext) -> dict:
  """Set the user's blockchain knowledge level and refresh root-agent prompt."""
  fallback_applied = False
  try:
    normalized_level = normalize_knowledge_level(level)
  except ValueError:
    normalized_level = DEFAULT_LEVEL
    fallback_applied = True

  tool_context.state[KNOWLEDGE_LEVEL_STATE_KEY] = normalized_level
  change_current_level(normalized_level)
  apply_blockchain_prompt_state_to_agent(root_agent)

  label = get_level_label(normalized_level)
  return {
    "ok": not fallback_applied,
    "knowledgeLevel": normalized_level,
    "knowledgeLevelLabel": label,
    "message": (
      f"Knowledge level updated to {label} (Level {normalized_level})."
      if not fallback_applied
      else "Invalid level provided. Falling back to Beginner (Level 1)."
    ),
  }

root_agent = LlmAgent(
    name="blockchain_agent",
    model=LiteLlm(model="claude-sonnet-5", api_key=ANTHROPIC_API_KEY),
    description=(
        "You are an agent expert in blockchain, helping users interact with blockchain environments."
    ),
    instruction=BLOCKCHAIN_AGENT_INSTRUCTION,
    before_tool_callback=check_user_level,
    tools=[setLevel],
    sub_agents=[
        info_agent,
        metamask_agent,
        contract_agent,
        defi_agent
    ]
)

relevance_classifier = LlmAsAJudge()
activity_logger = ActivityLoggerPlugin()

runner = Runner(
  agent=root_agent,
  app_name=APP_NAME,
  session_service=session_service,
  artifact_service=artifact_service,
  plugins=[activity_logger, relevance_classifier],
)


MCP_TOOLSETS = [
  blockchain_info_mcp_toolset,
  metamask_mcp_toolset,
  contract_mcp_toolset,
  defi_mcp_toolset
]


async def ensure_session(user_id: str = USER_ID, session_id: str = SESSION_ID):
  existing = await session_service.get_session(
    app_name=APP_NAME,
    user_id=user_id,
    session_id=session_id,
  )
  if existing is not None:
    return existing

  return await session_service.create_session(
    app_name=APP_NAME,
    user_id=user_id,
    session_id=session_id,
    state={KNOWLEDGE_LEVEL_STATE_KEY: DEFAULT_LEVEL},
  )


def close_mcp_toolsets() -> None:
  for toolset in MCP_TOOLSETS:
    try:
      close_result = toolset.close()
      if inspect.isawaitable(close_result):
        asyncio.run(close_result)
    except Exception as close_error:
      print(f"Warning while closing MCP toolset: {close_error}")


async def async_main() -> None:
  await ensure_session()
  query = "Hello, summarize which blockchain tasks you can help with."
  content = types.Content(role="user", parts=[types.Part(text=query)])

  print(f"User Query: {query}")
  async for event in runner.run_async(
    user_id=USER_ID,
    session_id=SESSION_ID,
    new_message=content,
  ):
    print(event)


if __name__ == '__main__':
  try:
    asyncio.run(async_main())
  except Exception as e:
    print(f"An error occurred: {e}")
  finally:
    close_mcp_toolsets()