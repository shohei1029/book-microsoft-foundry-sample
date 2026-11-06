"""Sample 3-2: invoke tools from a Microsoft Foundry toolbox."""

import asyncio
from contextlib import AsyncExitStack
from pathlib import Path
import sys

from agent_framework import Agent, Content, MCPStdioTool
from agent_framework.foundry import FoundryToolbox
from azure.identity import DefaultAzureCredential

from sample_support import PROJECT_ENDPOINT, open_client, parse_args


async def main():
    args = parse_args(__doc__, allow_toolbox=True)
    toolbox_name = args.toolbox_name or "offline-fixture"
    replies = [
        [Content.from_function_call("cost-1", "estimate_event_cost", arguments={"participants": 24})],
        "24200 JPY",
    ]
    async with AsyncExitStack() as stack:
        credential = stack.enter_context(DefaultAzureCredential())
        client = await stack.enter_async_context(open_client(args, replies))
        mcp_session = None
        if args.offline:
            fixture = await stack.enter_async_context(MCPStdioTool(
                name="toolbox_fixture",
                command=sys.executable,
                args=[str(Path(__file__).with_name("02_mcp_tool.py")), "--mcp-server"],
            ))
            mcp_session = fixture.session
        question = (
            "Use the toolbox to estimate event cost for 24 participants."
            if args.offline else
            "Use the toolbox to find the official Python 3 documentation. Include the source URL."
        )

        # %% SAMPLE START: 4 - Foundry toolbox
        toolbox = FoundryToolbox(
            credential,
            url=f"{PROJECT_ENDPOINT}/toolboxes/{toolbox_name}/mcp?api-version=v1",
            name=toolbox_name,
            session=mcp_session,
        )
        async with toolbox:
            agent = Agent(
                client=client,
                name="toolbox_assistant",
                instructions="Call an appropriate toolbox tool once, then answer from its result.",
                tools=toolbox,
                default_options={"store": False},
            )
            result = await agent.run(question)
        # %% SAMPLE END

        assert result.text.strip()
        tool_results = [
            content
            for message in result.messages
            for content in message.contents
            if content.type == "function_result"
        ]
        assert tool_results, "The agent must actually invoke a toolbox tool."
        if args.offline:
            assert "24200" in result.text
            print("PASS: FoundryToolbox with real MCP fixture; Entra/remote toolbox not exercised")
        else:
            assert "docs.python.org" in result.text, result.text
            print("PASS: live FoundryToolbox discovery and agent tool invocation")
        print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
