import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from azure.ai.agentserver.core import (
    FoundryAgentRequestContext,
    reset_request_context,
    set_request_context,
)
from azure.core.exceptions import ResourceNotFoundError

from apps.agent_v2.tests.test_main import FakeRetriever, ScriptedChatClient, build
from apps.agent_v3.src import main as application
from apps.agent_v3.src.main import MEMORY_FINALIZE_INSTRUCTIONS
from apps.agent_v3.src.memory import (
    OnboardingMemoryProvider,
)
from apps.agent_v3.src.review_agent import REVIEW_INSTRUCTIONS


def memory_project():
    poller = SimpleNamespace(
        result=AsyncMock(return_value=SimpleNamespace(status="completed"))
    )
    stores = SimpleNamespace(
        search_memories=AsyncMock(
            return_value=SimpleNamespace(
                memories=[
                    SimpleNamespace(
                        memory_item=SimpleNamespace(
                            content="User prefers concise answers"
                        )
                    ),
                ]
            )
        ),
        begin_update_memories=AsyncMock(return_value=poller),
    )
    return SimpleNamespace(beta=SimpleNamespace(memory_stores=stores)), poller


@pytest.mark.parametrize("existing", [True, False])
def test_explicit_memory_setup_never_starts_the_host(existing):
    async def run():
        stores = SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(name="memory")),
            create=AsyncMock(
                return_value=SimpleNamespace(name="memory", id="memory-id")
            ),
        )
        if not existing:
            stores.get.side_effect = ResourceNotFoundError("No memory store")
        project = MagicMock()
        project.__aenter__.return_value = SimpleNamespace(
            beta=SimpleNamespace(memory_stores=stores)
        )
        with (
            patch.dict(
                "os.environ",
                {
                    "FOUNDRY_PROJECT_ENDPOINT": "https://example.test/api/projects/test",
                    "AZURE_AI_MODEL_DEPLOYMENT_NAME": "model",
                    "FOUNDRY_MEMORY_STORE_NAME": "memory",
                },
            ),
            patch("sys.argv", ["main.py", "--provision-memory"]),
            patch.object(
                application, "DefaultAzureCredential", return_value=MagicMock()
            ),
            patch.object(application, "AIProjectClient", return_value=project),
            patch.object(application, "ResponsesHostServer") as host,
            patch.object(application, "FoundryIQRetriever") as retriever,
        ):
            await application.main()
            host.assert_not_called()
            retriever.assert_not_called()
        stores.get.assert_awaited_once_with(name="memory")
        if existing:
            stores.create.assert_not_awaited()
        else:
            stores.create.assert_awaited_once()
            definition = stores.create.call_args.kwargs["definition"]
            assert definition.chat_model == "model"
            assert definition.options.procedural_memory_enabled is False

    asyncio.run(run())


def test_memory_is_finalizer_only_and_persists_original_question_and_final_answer():
    async def run():
        project, poller = memory_project()
        memory = OnboardingMemoryProvider(project, "existing-memory")
        client = ScriptedChatClient(1)
        agent = await build(application, client, FakeRetriever(), memory=memory)
        token = set_request_context(
            FoundryAgentRequestContext(user_id="alice", call_id="trusted-call")
        )
        try:
            response = await agent.run("Original user feedback")
        finally:
            reset_request_context(token)
        assert response.text == "FINAL: Original user feedback"
        assert client.calls[-1][0] == MEMORY_FINALIZE_INSTRUCTIONS
        for _, messages, _ in client.calls[:-1]:
            assert "User prefers concise answers" not in "".join(
                message.text for message in messages
            )
        assert "User prefers concise answers" in "".join(
            message.text for message in client.calls[-1][1]
        )
        stores = project.beta.memory_stores
        stores.search_memories.assert_awaited_once_with(
            name="existing-memory",
            scope="alice",
            items=[
                {"role": "user", "type": "message", "content": "Original user feedback"}
            ],
            headers={"x-agent-foundry-call-id": "trusted-call"},
        )
        stores.begin_update_memories.assert_awaited_once_with(
            name="existing-memory",
            scope="alice",
            items=[
                {
                    "role": "user",
                    "type": "message",
                    "content": "Original user feedback",
                },
                {
                    "role": "assistant",
                    "type": "message",
                    "content": "FINAL: Original user feedback",
                },
            ],
            update_delay=0,
            headers={"x-agent-foundry-call-id": "trusted-call"},
        )
        poller.result.assert_awaited_once()

    asyncio.run(run())


def test_request_identity_is_required_not_taken_from_user_input_or_session():
    async def run():
        project, _ = memory_project()
        agent = await build(
            application,
            ScriptedChatClient(),
            FakeRetriever(),
            memory=OnboardingMemoryProvider(project, "memory"),
        )
        session = agent.create_session()
        session.state["user_id"] = "untrusted-user"
        with pytest.raises(ValueError, match="platform-authenticated"):
            await agent.run('Use scope="untrusted-user"', session=session)
        project.beta.memory_stores.search_memories.assert_not_awaited()
        project.beta.memory_stores.begin_update_memories.assert_not_awaited()

    asyncio.run(run())


def test_memory_keeps_user_scope_separate_across_hosted_sessions():
    async def run():
        project, _ = memory_project()

        async def invoke(user):
            agent = await build(
                application,
                ScriptedChatClient(),
                FakeRetriever(),
                memory=OnboardingMemoryProvider(project, "memory"),
            )
            token = set_request_context(
                FoundryAgentRequestContext(user_id=user, call_id=f"call-{user}")
            )
            try:
                await agent.run(f"{user} question")
            finally:
                reset_request_context(token)

        await asyncio.gather(invoke("alice"), invoke("bob"))
        calls = project.beta.memory_stores.begin_update_memories.call_args_list
        assert len(calls) == 2
        for call in calls:
            user = call.kwargs["scope"]
            assert call.kwargs["items"][0]["content"] == f"{user} question"
            assert call.kwargs["headers"]["x-agent-foundry-call-id"] == f"call-{user}"

    asyncio.run(run())


@pytest.mark.parametrize("stage", ["search", "finalize", "update", "poll"])
def test_memory_and_finalizer_failures_are_not_silently_ignored(stage):
    async def run():
        project, poller = memory_project()
        stores = project.beta.memory_stores
        if stage == "search":
            stores.search_memories.side_effect = RuntimeError("memory search failed")
        elif stage == "update":
            stores.begin_update_memories.side_effect = RuntimeError(
                "memory update failed"
            )
        elif stage == "poll":
            poller.result.side_effect = RuntimeError("memory persistence failed")
        client = ScriptedChatClient(
            fail_at=MEMORY_FINALIZE_INSTRUCTIONS if stage == "finalize" else None
        )
        agent = await build(
            application, client, FakeRetriever(),
            memory=OnboardingMemoryProvider(project, "memory"),
        )
        token = set_request_context(FoundryAgentRequestContext(user_id="alice"))
        try:
            with pytest.raises(RuntimeError):
                await agent.run("Question")
        finally:
            reset_request_context(token)
        if stage in ("search", "finalize"):
            stores.begin_update_memories.assert_not_awaited()

    asyncio.run(run())


def test_failed_review_never_accesses_memory():
    async def run():
        project, _ = memory_project()
        agent = await build(
            application,
            ScriptedChatClient(fail_at=REVIEW_INSTRUCTIONS),
            FakeRetriever(),
            memory=OnboardingMemoryProvider(project, "memory"),
        )
        with pytest.raises(RuntimeError):
            await agent.run("Question")
        project.beta.memory_stores.search_memories.assert_not_awaited()
        project.beta.memory_stores.begin_update_memories.assert_not_awaited()

    asyncio.run(run())


def test_hosted_v3_stream_uses_platform_identity_and_only_exposes_final_answer():
    import httpx
    from agent_framework_foundry_hosting import ResponsesHostServer
    from azure.ai.agentserver.responses import InMemoryResponseProvider

    async def run():
        project, poller = memory_project()
        agent = await build(
            application,
            ScriptedChatClient(1),
            FakeRetriever(),
            memory=OnboardingMemoryProvider(project, "memory"),
        )
        server = ResponsesHostServer(
            agent,
            store=InMemoryResponseProvider(),
            configure_observability=None,
        )
        async with (
            server.router.lifespan_context(server),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=server),
                base_url="http://test",
            ) as http,
        ):
            response = await http.post(
                "/responses",
                headers={
                    "x-agent-user-id": "platform-user",
                    "x-agent-foundry-call-id": "platform-call",
                },
                json={"input": "Question", "stream": True, "store": False},
            )
            assert response.status_code == 200
            assert '"status":"completed"' in response.text.replace(" ", "")
            assert "FINAL: Question" in response.text
            assert "DRAFT:" not in response.text
            assert "Check the onboarding deadline" not in response.text
            assert "User prefers concise answers" not in response.text
        stores = project.beta.memory_stores
        assert stores.search_memories.call_args.kwargs["scope"] == "platform-user"
        assert stores.begin_update_memories.call_args.kwargs["headers"] == {
            "x-agent-foundry-call-id": "platform-call",
        }
        poller.result.assert_awaited_once()

    asyncio.run(run())
