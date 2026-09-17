"""Agent responsible for handling DeFi operations.

  This agent send transaction data to the wallet to perform DeFi operations,
  like lending, borrowing, withdrawing, and repaying on supported protocols and networks.
  This agent is available only for at least intermediate users.
"""

from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import MCPToolset
from google.adk.tools.mcp_tool import StdioConnectionParams
from mcp import StdioServerParameters
from pathlib import Path
import sys
from utils.policy_utils import check_user_level
from utils.prompts import DEFI_AGENT_INSTRUCTION

MCP_SERVER_PATH = (
  Path(__file__).resolve().parents[4] / "mcp" / "DeFiTools" / "server.py"
)


def _mcp_python_executable() -> str:
  project_root = Path(__file__).resolve().parents[5]
  windows_python = project_root / ".venv" / "Scripts" / "python.exe"
  unix_python = project_root / ".venv" / "bin" / "python"
  if windows_python.exists():
    return str(windows_python)
  if unix_python.exists():
    return str(unix_python)
  return sys.executable

defi_mcp_toolset = MCPToolset(
  connection_params=StdioConnectionParams(
    server_params=StdioServerParameters(
      command=_mcp_python_executable(),
      args=[str(MCP_SERVER_PATH)],
    ),
    timeout=180.0,
  )
)

defi_agent = LlmAgent(
    #model=LiteLlm(model="claude-haiku-4-5-20251001"),
    model=LiteLlm(model="claude-sonnet-5"),
    name="defi_agent",
    description="Handle DeFi operations.",
    instruction=DEFI_AGENT_INSTRUCTION,
    before_tool_callback=check_user_level,
    tools=[
      defi_mcp_toolset,
    ],
)
