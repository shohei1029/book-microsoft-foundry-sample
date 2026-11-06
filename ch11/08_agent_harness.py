"""Sample 6: create a harness agent with built-in todo management."""

import asyncio

from agent_framework import Agent, Content, TodoProvider, create_harness_agent

from sample_support import ScriptedChatClient, open_client, parse_args


async def main():
    args = parse_args(__doc__)
    replies = [
        [Content.from_function_call(
            "add-1",
            "todos_add",
            arguments={"todos": [{"title": "Draft plan", "description": "Prepare an event agenda."}]},
        )],
        [Content.from_function_call(
            "complete-1",
            "todos_complete",
            arguments={
                "items": [{
                    "id": 1,
                    "reason": "Prepared a welcome, workshop, and wrap-up agenda.",
                }]
            },
        )],
        "Agenda: welcome, workshop, wrap-up.",
    ]
    async with open_client(args, replies) as client:
        # %% SAMPLE START: 9 - Agent harness
        todos = TodoProvider()
        agent = create_harness_agent(
            client,
            name="event_planner",
            agent_instructions=(
                "Use todos_add to record one task named Draft plan. "
                "Create a short event agenda, then mark the task complete with todos_complete. "
                "Return the agenda."
            ),
            todo_provider=todos,
            max_context_window_tokens=8_192,
            max_output_tokens=1_024,
            disable_mode=True,
            disable_file_memory=True,
            disable_web_search=True,
            default_options={"store": False},
        )
        # %% SAMPLE END

        assert isinstance(agent, Agent)
        session = agent.create_session()
        result = await agent.run("Prepare a short internal event agenda.", session=session)
        items = await todos.store.load_items(session, source_id=todos.source_id)
        assert items and all(item.is_complete for item in items)
        assert result.text.strip()
        if args.offline:
            assert isinstance(client, ScriptedChatClient)
            assert len(client.requests) == 3
            assert "Agenda:" in result.text
        print(result.text)
        print([(item.title, item.is_complete) for item in items])
        print("PASS: harness factory, built-in todos, and completion")


if __name__ == "__main__":
    asyncio.run(main())
