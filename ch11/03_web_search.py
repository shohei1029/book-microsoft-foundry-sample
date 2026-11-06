"""Sample 3-1: use the model provider's web search tool in Foundry."""

import asyncio

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient

from sample_support import ScriptedChatClient, open_client, parse_args


async def main():
    args = parse_args(__doc__)
    async with open_client(args, ["Python documentation: https://docs.python.org/3/"]) as client:
        # %% SAMPLE START: 3 - Foundry Web Search
        web_search = FoundryChatClient.get_web_search_tool(search_context_size="low")
        agent = Agent(
            client=client,
            instructions=(
                "Use web search to find the official Python documentation. "
                "Answer briefly and include the source URL."
            ),
            tools=[web_search],
            default_options={"store": False, "tool_choice": "required"},
        )
        result = await agent.run("Find the official Python 3 documentation on the web.")
        # %% SAMPLE END

        assert "docs.python.org" in result.text, result.text
        if args.offline:
            assert isinstance(client, ScriptedChatClient)
            assert client.options[0]["tools"] == [web_search]
            assert client.options[0]["tool_choice"] == "required"
            print("PASS: web search factory and request options (scripted response; no web request)")
        else:
            citations = [
                annotation
                for message in result.messages
                for content in message.contents
                for annotation in (content.annotations or [])
            ]
            assert citations, "The response must contain provider-produced web citations."
            print("PASS: real Foundry web search with citations")
        print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
