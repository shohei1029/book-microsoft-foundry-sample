"""Samples 5, 9, and 10: Agent initialization and AgentSession lifecycle."""

import asyncio
import json

from agent_framework import Agent, AgentSession, Content

from sample_support import ScriptedChatClient, open_client, parse_args

tool_calls = []


def estimate_cost(participants: int) -> int:
    """Return the event cost in JPY for the given participant count."""
    tool_calls.append(participants)
    return 5_000 + participants * 800


async def main():
    args = parse_args(__doc__)
    replies = [
        [Content.from_function_call("cost-1", "estimate_cost", arguments={"participants": 24})],
        ["24200 JPY"],
    ]
    async with open_client(args, replies) as client:
        # %% SAMPLE START: 6 - Agent initialization
        agent = Agent(
            name="event_assistant",
            client=client,
            instructions="Estimate event costs. Always calculate costs with estimate_cost.",
            tools=[estimate_cost],
            default_options={"store": False},
        )
        # %% SAMPLE END

        # %% SAMPLE START: 13 - AgentSession state
        session = agent.create_session()
        session.state["app"] = {
            "tenant_id": "tenant-001",
            "plan": "premium",
        }
        result = await agent.run(
            "Estimate the cost for 24 participants.",
            session=session,
        )
        # %% SAMPLE END

        # %% SAMPLE START: 14 - AgentSession save and restore
        session_data = session.to_dict()
        restored_session = AgentSession.from_dict(json.loads(json.dumps(session_data)))
        # %% SAMPLE END

        assert result.text.strip()
        assert tool_calls and all(participants == 24 for participants in tool_calls)
        assert "24200" in result.text.replace(",", "")
        assert restored_session.session_id == session.session_id
        assert restored_session.state["app"] == session.state["app"]
        if args.offline:
            assert isinstance(client, ScriptedChatClient)
            assert tool_calls == [24]
            assert len(client.requests) == 2
        print(result.text)
        print("PASS: Agent tool call; session state; dict save and restore")


if __name__ == "__main__":
    asyncio.run(main())
