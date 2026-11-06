"""Sample 2: connect an MCPStdioTool to a local stdio MCP server."""

import asyncio
import json
from pathlib import Path
import sys

from agent_framework import MCPStdioTool
from mcp.server.fastmcp import FastMCP

from sample_support import check_environment

mcp_server = FastMCP("event-tools")


@mcp_server.tool()
def estimate_event_cost(participants: int) -> int:
    """Estimate an event cost in JPY."""
    return 5_000 + participants * 800


# %% SAMPLE START: 2 - MCP server tool
event_tools = MCPStdioTool(
    name="event_tools",
    command=sys.executable,
    args=[str(Path(__file__).resolve()), "--mcp-server"],
    description="Event planning tools exposed by a local MCP server.",
    allowed_tools=["estimate_event_cost"],
)
# %% SAMPLE END


async def main():
    check_environment()
    async with event_tools:
        names = [function.name for function in event_tools.functions]
        result = await event_tools.call_tool("estimate_event_cost", participants=24)
        assert names == ["estimate_event_cost"]
        assert isinstance(result, list)
        assert len(result) == 1 and result[0].text is not None
        assert json.loads(result[0].text) == {"result": 24200}
        print([content.text for content in result])
        print("PASS: MCP stdio startup, discovery, and tool invocation")


if __name__ == "__main__":
    if "--mcp-server" in sys.argv:
        mcp_server.run(transport="stdio")
    else:
        asyncio.run(main())
