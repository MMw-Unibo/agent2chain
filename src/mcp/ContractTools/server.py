import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from dotenv import load_dotenv

# MCP Server Imports
from mcp import types as mcp_types
from mcp.server.lowlevel import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio

# ADK <-> MCP Conversion Utility
from google.adk.tools.mcp_tool.conversion_utils import adk_to_mcp_tool_type
from google.adk.tools import FunctionTool


SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
    sys.path.append(str(SRC_ROOT))

from agents.BlockchainAgent.plugin.activity_logger_plugin import log_activity


def _log(*args, **kwargs):
    try:
        print(*args, file=sys.stderr, flush=True, **kwargs)
    except Exception:
        pass


def _load_tool_function(module_filename: str, function_name: str):
    module_path = Path(__file__).resolve().parent / module_filename
    spec = importlib.util.spec_from_file_location(function_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module '{module_filename}'")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, function_name)


writeContract = _load_tool_function("writeContract.py", "writeContract")
scanContract = _load_tool_function("scanContract.py", "scanContract")
listDeployedContracts = _load_tool_function("listDeployedContracts.py", "listDeployedContracts")
describeContract = _load_tool_function("describeContract.py", "describeContract")

load_dotenv()

ADK_TOOLS = [
    FunctionTool(writeContract),
    FunctionTool(scanContract),
    FunctionTool(listDeployedContracts),
    FunctionTool(describeContract),
]
ADK_TOOLS_BY_NAME = {tool.name: tool for tool in ADK_TOOLS}

_log("Creating MCP Server instance...")
app = Server("ContractToolsServer")

@app.list_tools()
async def list_mcp_tools() -> list[mcp_types.Tool]:
    """MCP handler to list tools this server exposes."""
    _log("MCP Server: Received list_tools request.")
    mcp_tools = [adk_to_mcp_tool_type(tool) for tool in ADK_TOOLS]
    _log(
        "MCP Server: Advertising tools:",
        ", ".join(tool.name for tool in mcp_tools),
    )
    return mcp_tools

@app.call_tool()
async def call_mcp_tool(
    name: str, arguments: dict | None
) -> list[mcp_types.Content]:
    """MCP handler to execute a tool call requested by an MCP client."""
    safe_arguments = arguments or {}
    _log(f"MCP Server: Received call_tool request for '{name}' with args: {safe_arguments}")
    log_activity(
        "tool_invocation",
        {
            "server": app.name,
            "tool_name": name,
            "arguments": safe_arguments,
        },
    )

    if name in ADK_TOOLS_BY_NAME:
        adk_tool_to_expose = ADK_TOOLS_BY_NAME[name]
        try:
            adk_tool_response = await adk_tool_to_expose.run_async(
                args=safe_arguments,
                tool_context=None,
            )
            _log(f"MCP Server: ADK tool '{name}' executed. Response: {adk_tool_response}")
            log_activity(
                "tool_response",
                {
                    "server": app.name,
                    "tool_name": name,
                    "result": adk_tool_response,
                },
            )
            response_text = json.dumps(adk_tool_response, indent=2)
            return [mcp_types.TextContent(type="text", text=response_text)]

        except Exception as e:
            _log(f"MCP Server: Error executing ADK tool '{name}': {e}")
            log_activity(
                "tool_response",
                {
                    "server": app.name,
                    "tool_name": name,
                    "error": str(e),
                },
            )
            error_text = json.dumps({"error": f"Failed to execute tool '{name}': {str(e)}"})
            return [mcp_types.TextContent(type="text", text=error_text)]
    else:
        _log(f"MCP Server: Tool '{name}' not found/exposed by this server.")
        log_activity(
            "tool_response",
            {
                "server": app.name,
                "tool_name": name,
                "error": "Tool not implemented by this server",
            },
        )
        error_text = json.dumps({"error": f"Tool '{name}' not implemented by this server."})
        return [mcp_types.TextContent(type="text", text=error_text)]

async def run_mcp_stdio_server():
    """Runs the MCP server, listening for connections over standard input/output."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        _log("MCP Stdio Server: Starting handshake with client...")
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=app.name,
                server_version="0.1.0",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
        _log("MCP Stdio Server: Run loop finished or client disconnected.")

if __name__ == "__main__":
    _log("Launching MCP Server to expose ADK tools via stdio...")
    try:
        asyncio.run(run_mcp_stdio_server())
    except KeyboardInterrupt:
        _log("\nMCP Server (stdio) stopped by user.")
    except Exception as e:
        _log(f"MCP Server (stdio) encountered an error: {e}")
