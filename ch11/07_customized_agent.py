"""Samples 5-2 and 5-3: raw agent logic and middleware/telemetry layers."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal, TypeVar, overload

from agent_framework import (
    AgentMiddlewareLayer,
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    AgentSession,
    BaseAgent,
    ChatOptions,
    ChatResponse,
    CompactionStrategy,
    FinishReason,
    ResponseStream,
    SupportsChatGetResponse,
    TokenizerProtocol,
    ToolTypes,
    agent_middleware,
    normalize_messages,
)
from agent_framework.observability import AgentTelemetryLayer
from pydantic import BaseModel

from sample_support import ScriptedChatClient, open_client, parse_args

AgentStream = ResponseStream[AgentResponseUpdate, AgentResponse[Any]]
Tools = ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]]
ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


# %% SAMPLE START: 7 - Raw agent implementation
class RawCustomizedAgent(BaseAgent):
    AGENT_PROVIDER_NAME = "mycompany.myagent"

    def __init__(
        self,
        client: SupportsChatGetResponse[Any],
        *,
        middleware=None,
        context_providers=None,
        default_options=None,
        name="customized_agent",
        **kwargs,
    ) -> None:
        super().__init__(
            name=name,
            middleware=middleware,
            context_providers=context_providers,
            **kwargs,
        )
        self.client = client
        self._default_options = dict(default_options or {})

    @property
    def default_options(self) -> dict[str, Any]:
        return self._default_options

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = False,
        session: AgentSession | None = None,
        tools: Tools | None = None,
        options: ChatOptions[ResponseModelT],
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[AgentResponse[ResponseModelT]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = False,
        session: AgentSession | None = None,
        tools: Tools | None = None,
        options: ChatOptions[None] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[AgentResponse[Any]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        tools: Tools | None = None,
        options: ChatOptions[Any] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> AgentStream: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        tools: Tools | None = None,
        options: ChatOptions[Any] | ChatOptions[None] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[AgentResponse[Any]] | AgentStream:
        if self.context_providers:
            raise NotImplementedError("Context provider execution is outside this minimal example.")
        if session is None:
            raise ValueError("Pass a session with state['experience_level'].")
        experience_level = session.state.get("experience_level")
        if experience_level == "beginner":
            instructions = "Explain in simple terms, define jargon, and include one short example."
        elif experience_level == "experienced":
            instructions = "Assume technical experience and focus on trade-offs and practical pitfalls."
        else:
            raise ValueError("session.state['experience_level'] must be 'beginner' or 'experienced'.")

        run_options = {
            **self.default_options, **(options or {}),
            "instructions": instructions, "store": False,
        }
        if tools is not None:
            run_options["tools"] = tools
        client_kwargs = {**(client_kwargs or {}), "session": session}
        if stream:
            response = self.client.get_response(
                normalize_messages(messages), stream=True, options=run_options,
                compaction_strategy=compaction_strategy, tokenizer=tokenizer,
                function_invocation_kwargs=function_invocation_kwargs,
                client_kwargs=client_kwargs,
            )
            return response.map(
                lambda update: AgentResponseUpdate(
                    contents=update.contents,
                    role=update.role,
                    author_name=update.author_name,
                    agent_id=self.id,
                    response_id=update.response_id,
                    message_id=update.message_id,
                    created_at=update.created_at,
                    finish_reason=(
                        FinishReason(update.finish_reason) if update.finish_reason is not None else None
                    ),
                ),
                finalizer=lambda _: self._run(response.get_final_response()),
            )
        return self._run(self.client.get_response(
            normalize_messages(messages), options=run_options,
            compaction_strategy=compaction_strategy, tokenizer=tokenizer,
            function_invocation_kwargs=function_invocation_kwargs,
            client_kwargs=client_kwargs,
        ))

    async def _run(self, pending: Awaitable[ChatResponse[Any]]) -> AgentResponse[Any]:
        response = await pending
        return AgentResponse(
            messages=response.messages,
            response_id=response.response_id,
            agent_id=self.id,
            created_at=response.created_at,
            finish_reason=(
                FinishReason(response.finish_reason) if response.finish_reason is not None else None
            ),
            usage_details=response.usage_details,
            value=response.value,
        )
# %% SAMPLE END


# %% SAMPLE START: 8 - Public agent with middleware and telemetry
class CustomizedAgent(AgentMiddlewareLayer, AgentTelemetryLayer, RawCustomizedAgent):
    pass
# %% SAMPLE END


async def main() -> None:
    args = parse_args(__doc__)
    replies = [
        "An SDK is a toolkit that helps you use a service. For example, it can send an API request.",
        "An SDK trades direct protocol control for convenience; watch version compatibility.",
    ]
    events = []

    @agent_middleware
    async def track_run(context, call_next):
        events.append("before")
        await call_next()
        events.append("after")

    async with open_client(args, replies) as client:
        # %% SAMPLE START: 8 - Run the public agent with session state
        agent = CustomizedAgent(client, middleware=[track_run])
        session = agent.create_session()
        session.state["experience_level"] = "beginner"
        response = await agent.run("What is an SDK?", session=session)
        # %% SAMPLE END

        assert response.text.strip()
        assert response.agent_id == agent.id
        assert session.state["experience_level"] == "beginner"
        print(response.text)

        session.state["experience_level"] = "experienced"
        stream = agent.run("Explain SDK design trade-offs.", session=session, stream=True)
        experienced_response = await stream.get_final_response()
        assert experienced_response.text.strip()
        assert experienced_response.agent_id == agent.id
        assert session.state["experience_level"] == "experienced"
        print(experienced_response.text)

        if isinstance(client, ScriptedChatClient):
            assert response.text == replies[0]
            assert experienced_response.text == replies[1]
            assert len(client.requests) == 2
            first_instructions = client.options[0]["instructions"]
            second_instructions = client.options[1]["instructions"]
            assert "simple terms" in first_instructions
            assert "trade-offs" in second_instructions
            assert "simple terms" not in second_instructions
            assert len(client.requests[1]) == 1
        assert session.state == {"experience_level": "experienced"}
        assert events == ["before", "after", "before", "after"]
        assert agent.otel_provider_name == RawCustomizedAgent.AGENT_PROVIDER_NAME
        print("PASS: Raw agent calls the client; public agent applies middleware and telemetry layers")


if __name__ == "__main__":
    asyncio.run(main())
