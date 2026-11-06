"""Sample 16: inject profile context and update session-scoped provider state."""

import asyncio

from agent_framework import Agent, ContextProvider, Message, SessionContext

from sample_support import ScriptedChatClient, open_client, parse_args


# %% SAMPLE START: 24 - ContextProvider subclass
class ProfileProvider(ContextProvider):
    def __init__(self, profile: str):
        super().__init__("user_profile")
        self.profile = profile

    async def before_run(self, *, agent, session, context: SessionContext, state):
        context.extend_instructions(
            self.source_id,
            "Tailor the explanation to the supplied profile.",
        )
        context.extend_messages(self, [Message("user", [self.profile])])

    async def after_run(self, *, agent, session, context: SessionContext, state):
        if context.response and context.response.text:
            state["completed_runs"] = state.get("completed_runs", 0) + 1
# %% SAMPLE END


async def main():
    args = parse_args(__doc__)
    profile = "The user is a Python developer who prefers short practical examples."
    replies = ["A Python-oriented explanation.", "Another concise explanation.", "A fresh explanation."]
    async with open_client(args, replies) as client:
        agent = Agent(
            client=client,
            name="onboarding_assistant",
            instructions="Answer in at most two sentences.",
            context_providers=[ProfileProvider(profile)],
            default_options={"store": False},
        )
        session = agent.create_session()
        first = await agent.run("What is an SDK?", session=session)
        second = await agent.run("What is a client library?", session=session)
        assert first.text.strip() and second.text.strip()
        assert session.state["user_profile"]["completed_runs"] == 2

        other_session = agent.create_session()
        await agent.run("What is an API?", session=other_session)
        assert other_session.state["user_profile"]["completed_runs"] == 1
        assert session.state["user_profile"]["completed_runs"] == 2
        if args.offline:
            assert isinstance(client, ScriptedChatClient)
            for messages in client.requests:
                profiles = [message for message in messages if message.text == profile]
                assert profiles
                assert profiles[-1].additional_properties["_attribution"]["source_id"] == "user_profile"
        print(first.text)
        print(second.text)
        print("PASS: context hooks, attribution, and session isolation")


if __name__ == "__main__":
    asyncio.run(main())
