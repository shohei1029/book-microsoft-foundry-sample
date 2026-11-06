import ast
import asyncio
import json
from contextlib import nullcontext
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest
from agent_framework import (
    Agent,
    AgentExecutor,
    AgentResponse,
    BaseAgent,
    BaseChatClient,
    ChatResponse,
    ChatResponseUpdate,
    ContextProvider,
    Message,
    ResponseStream,
    WorkflowAgent,
)
from azure.core.credentials import AccessToken
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from azure.core.pipeline.transport import AsyncHttpTransport
from azure.core.rest import AsyncHttpResponse
from azure.search.documents import ApiVersion
from azure.search.documents.knowledgebases.aio import KnowledgeBaseRetrievalClient
from pydantic import ValidationError

from apps.agent_v2.src import main as application
from apps.agent_v2.src.main import FINALIZE_INSTRUCTIONS
from apps.agent_v2.src.rag_agent import (
    RAG_INSTRUCTIONS,
    REVISION_INSTRUCTIONS,
)
from apps.agent_v2.src.review_agent import REVIEW_INSTRUCTIONS


class ScriptedChatClient(BaseChatClient):
    def __init__(self, required_revisions=0, fail_at=None, invalid_review=False):
        super().__init__()
        self.calls = []
        self.required_revisions = required_revisions
        self.fail_at = fail_at
        self.invalid_review = invalid_review

    def _inner_get_response(self, *, messages, stream, options, **kwargs):
        async def respond():
            await asyncio.sleep(0)
            instructions = options["instructions"]
            payload = list(messages)
            self.calls.append((instructions, payload, dict(options)))
            if instructions == self.fail_at:
                raise RuntimeError("Injected model failure")
            if instructions in (RAG_INSTRUCTIONS, REVISION_INSTRUCTIONS):
                data = json.loads(payload[0].text)
                text = f"DRAFT: {data['question']}: {len(data['retrievals'])}"
            elif instructions == REVIEW_INSTRUCTIONS:
                data = json.loads(payload[0].text)
                text = (
                    "not json"
                    if self.invalid_review
                    else json.dumps(
                        {
                            "needs_revision": data["revision_count"]
                            < self.required_revisions,
                            "feedback": "Check the onboarding deadline",
                            "answer": f"CHECKED: {data['question']}",
                            "revision_count": 999,
                        }
                    )
                )
            else:
                assert instructions.startswith(FINALIZE_INSTRUCTIONS)
                question = next(
                    message.text
                    for message in payload
                    if message.role == "user"
                    and not message.additional_properties.get("_attribution")
                )
                text = f"FINAL: {question}"
            return ChatResponse(messages=[Message("assistant", [text])])

        if stream:

            async def updates():
                response = await respond()
                yield ChatResponseUpdate(
                    role="assistant",
                    contents=response.messages[0].contents,
                    response_id="final-response",
                    message_id="final-message",
                )

            return ResponseStream(updates(), finalizer=ChatResponse.from_updates)
        return respond()


class FakeRetriever:
    def __init__(self):
        self.calls = []

    async def retrieve(self, query):
        self.calls.append(query)
        return {
            "query": query,
            "answer": "UNTRUSTED synthesis",
            "sources": [
                {
                    "ref_id": str(len(self.calls)),
                    "title": "Guide.md",
                    "content": f"RAW: {query}",
                }
            ],
            "raw_response": {"activity": ["retrieved"], "query": query},
        }


class MemoryFixture(ContextProvider):
    def __init__(self):
        super().__init__("test_memory")
        self.calls = []

    async def before_run(self, *, agent, session, context, state):
        self.calls.append(
            ("before", agent.name, session.state["onboarding"]["question"])
        )
        context.extend_messages(self, [Message("user", ["PRIVATE MEMORY"])])

    async def after_run(self, *, agent, session, context, state):
        self.calls.append(("after", agent.name, context.response.text))


@pytest.fixture(params=["agent_v2", "agent_v3"])
def version(request):
    main = import_module(f"apps.{request.param}.src.main")
    rag = import_module(f"apps.{request.param}.src.rag_agent")
    review = import_module(f"apps.{request.param}.src.review_agent")
    return main, SimpleNamespace(
        RagAgent=rag.RagAgent,
        ReviewAgent=review.ReviewAgent,
        ReviewResult=review.ReviewResult,
    )


@pytest.mark.parametrize("version_name", ["agent_v2", "agent_v3"])
def test_completed_stream_preserves_review_value_and_awaits_once(version_name):
    async def run():
        streaming = import_module(f"apps.{version_name}.src.streaming")
        review = import_module(f"apps.{version_name}.src.review_agent")
        result = review.ReviewResult(
            needs_revision=True,
            feedback="More evidence needed",
            answer="Draft",
            revision_count=1,
        )
        response = AgentResponse(
            messages=[
                Message(
                    "assistant", [result.model_dump_json()], author_name="review_agent"
                )
            ],
            value=result,
            agent_id="review-id",
            response_id="response-id",
        )
        produce = AsyncMock(return_value=response)
        stream = ResponseStream.from_awaitable(streaming.completed_stream(produce()))
        produce.assert_not_awaited()
        updates = [update async for update in stream]
        produce.assert_awaited_once()
        assert "".join(update.text for update in updates) == response.text
        assert updates[0].agent_id == "review-id"
        assert updates[0].author_name == "review_agent"
        final = await stream.get_final_response()
        assert final is response
        assert final.value is result
        assert await stream.get_final_response() is response
        produce.assert_awaited_once()

    asyncio.run(run())


@pytest.mark.parametrize("version_name", ["agent_v2", "agent_v3"])
def test_completed_stream_propagates_failure_before_emitting_updates(version_name):
    async def run():
        streaming = import_module(f"apps.{version_name}.src.streaming")
        produce = AsyncMock(side_effect=RuntimeError("Agent failed"))
        stream = ResponseStream.from_awaitable(streaming.completed_stream(produce()))
        with pytest.raises(RuntimeError, match="Agent failed"):
            await stream.__anext__()
        produce.assert_awaited_once()

    asyncio.run(run())


async def build(main, client, retriever, *, max_revisions=2, memory=None):
    client.client = SimpleNamespace(close=AsyncMock())
    retriever.close = AsyncMock()
    project = MagicMock()
    project.__aenter__.return_value = project
    with (
        patch.dict(
            "os.environ",
            {
                "FOUNDRY_PROJECT_ENDPOINT": "https://example.test/api/projects/test",
                "AZURE_AI_MODEL_DEPLOYMENT_NAME": "model",
                "AZURE_SEARCH_ENDPOINT": "https://search.example.test",
                "FOUNDRY_MEMORY_STORE_NAME": "memory",
                "MAX_REVISIONS": str(max_revisions),
            },
        ),
        patch("sys.argv", ["main.py"]),
        patch.object(main, "DefaultAzureCredential", return_value=MagicMock()),
        patch.object(main, "AIProjectClient", return_value=project),
        patch.object(main, "FoundryChatClient", return_value=client),
        patch.object(main, "FoundryIQRetriever", return_value=retriever),
        (
            patch.object(
                main,
                "OnboardingMemoryProvider",
                return_value=memory if memory is not None else MemoryFixture(),
            )
            if main.__name__.endswith("agent_v3.src.main")
            else nullcontext()
        ),
        patch.object(main, "ResponsesHostServer") as server,
    ):
        server.return_value.run_async = AsyncMock()
        try:
            await main.main()
        finally:
            retriever.close.assert_awaited_once()
            client.client.close.assert_awaited_once()
        agent = server.call_args.args[0]
        assert isinstance(agent, WorkflowAgent)
        return agent


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize(
    "required_revisions,max_revisions,expected",
    [(0, 2, 0), (1, 2, 1), (9, 2, 2), (9, 0, 0)],
)
def test_bounded_revision_loop_uses_shared_evidence_and_only_returns_final(
    version, streaming, required_revisions, max_revisions, expected
):
    async def run():
        main, workflow = version
        client = ScriptedChatClient(required_revisions)
        retriever = FakeRetriever()
        agent = await build(main, client, retriever, max_revisions=max_revisions)
        result = agent.run("Original question", stream=streaming)
        if streaming:
            assert isinstance(result, ResponseStream)
            updates = [update async for update in result]
            assert (
                "".join(update.text for update in updates) == "FINAL: Original question"
            )
            result = await result.get_final_response()
        else:
            result = await result
        assert result.text == "FINAL: Original question"
        assert isinstance(workflow.RagAgent(client, retriever), BaseAgent)
        assert isinstance(workflow.ReviewAgent(client), BaseAgent)
        assert not isinstance(workflow.RagAgent(client, retriever), Agent)
        assert len(retriever.calls) == expected + 1
        assert retriever.calls[0] == "Original question"
        assert all(
            "Check the onboarding deadline" in query for query in retriever.calls[1:]
        )
        assert [call[0] for call in client.calls[:-1]] == [
            RAG_INSTRUCTIONS,
            REVIEW_INSTRUCTIONS,
            *[
                instruction
                for _ in range(expected)
                for instruction in (REVISION_INSTRUCTIONS, REVIEW_INSTRUCTIONS)
            ],
        ]
        for instructions, messages, options in client.calls[:-1]:
            data = json.loads(messages[0].text)
            assert data["question"] == "Original question"
            assert data["user_input"][0]["contents"][0]["text"] == "Original question"
            assert "PRIVATE MEMORY" not in json.dumps(data)
            assert (
                data["retrievals"][0]["sources"][0]["content"]
                == "RAW: Original question"
            )
            assert data["retrievals"][0]["raw_response"]["activity"] == ["retrieved"]
            assert options["store"] is False
            if instructions == REVIEW_INSTRUCTIONS:
                assert options["response_format"] is workflow.ReviewResult
        final_input = [
            message
            for message in client.calls[-1][1]
            if not message.additional_properties.get("_attribution")
        ]
        assert final_input[0].text == "Original question"
        review_data = json.loads(final_input[1].text)
        assert review_data["revision_count"] == expected
        assert "DRAFT:" not in "".join(message.text for message in final_input)
        if main.__name__.endswith("agent_v3.src.main"):
            memory = next(
                provider
                for executor in agent.workflow.executors.values()
                if isinstance(executor, AgentExecutor)
                for provider in executor.agent.context_providers
                if isinstance(provider, MemoryFixture)
            )
            assert memory.calls == [
                ("before", "finalize_agent", "Original question"),
                ("after", "finalize_agent", "FINAL: Original question"),
            ]

    asyncio.run(run())


def test_each_turn_resets_workflow_state(version):
    async def run():
        main, _ = version
        client, retriever = ScriptedChatClient(1), FakeRetriever()
        agent = await build(main, client, retriever)
        results = [
            await agent.run("Alice question"),
            await agent.run("Bob question"),
        ]
        assert [response.text for response in results] == [
            "FINAL: Alice question",
            "FINAL: Bob question",
        ]
        second_turn_messages = [
            message.text
            for _, messages, _ in client.calls
            for message in messages
            if "Bob question" in message.text
        ]
        assert second_turn_messages
        assert all("Alice question" not in message for message in second_turn_messages)

    asyncio.run(run())


@pytest.mark.parametrize("bad", ["-1", "true", "1.5", ""])
def test_invalid_loop_limit_is_rejected(version, bad):
    async def run():
        main, _ = version
        with pytest.raises(ValueError):
            await build(main, ScriptedChatClient(), FakeRetriever(), max_revisions=bad)

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["retrieval", "rag", "review", "schema"])
def test_failures_stop_before_finalization(version, failure):
    async def run():
        main, _ = version
        client = ScriptedChatClient(
            fail_at={"rag": RAG_INSTRUCTIONS, "review": REVIEW_INSTRUCTIONS}.get(
                failure
            ),
            invalid_review=failure == "schema",
        )
        retriever = FakeRetriever()
        if failure == "retrieval":
            retriever.retrieve = AsyncMock(side_effect=RuntimeError("Retrieval failed"))
        agent = await build(main, client, retriever)
        with pytest.raises(ValidationError if failure == "schema" else RuntimeError):
            await agent.run("Question")
        assert not any(
            instructions.startswith(FINALIZE_INSTRUCTIONS)
            for instructions, _, _ in client.calls
        )
        if main.__name__.endswith("agent_v3.src.main"):
            assert not any(
                isinstance(provider, MemoryFixture) and provider.calls
                for executor in agent.workflow.executors.values()
                if isinstance(executor, AgentExecutor)
                for provider in executor.agent.context_providers
            )

    asyncio.run(run())


def test_missing_query_and_custom_agent_session_are_errors(version):
    main, workflow = version
    client, retriever = ScriptedChatClient(), FakeRetriever()

    async def run():
        workflow_agent = await build(main, client, retriever)
        with pytest.raises(ValueError, match="question"):
            await workflow_agent.run("")
        for agent in (
            workflow.RagAgent(client, retriever),
            workflow.ReviewAgent(client),
        ):
            with pytest.raises(ValueError, match="shared workflow session"):
                await agent.run("Question")

    asyncio.run(run())


@pytest.fixture(params=["agent_v2", "agent_v3"])
def iq_version(request):
    return import_module(f"apps.{request.param}.src.retrieval")


def iq_retriever(module, payload, *, status_code=200):
    credential = Mock(spec=AsyncTokenCredential)
    credential.get_token = AsyncMock(
        return_value=AccessToken("test-token", 4_102_444_800)
    )
    transport = AsyncMock(spec=AsyncHttpTransport)

    async def send(request, **kwargs):
        response = Mock(spec=AsyncHttpResponse)
        response.request = request
        response.status_code = status_code
        response.reason = "OK" if status_code == 200 else "Injected HTTP error"
        response.headers = {"content-type": "application/json"}
        response.content_type = "application/json"
        response.json.return_value = payload
        response.text.return_value = json.dumps(payload)
        return response

    transport.send.side_effect = send
    with patch.object(
        module,
        "KnowledgeBaseRetrievalClient",
        side_effect=lambda **kwargs: KnowledgeBaseRetrievalClient(
            **kwargs, transport=transport
        ),
    ) as factory:
        retriever = module.FoundryIQRetriever(
            credential, "https://search.example.com/", "onboarding knowledge", "source"
        )
    factory.assert_called_once_with(
        endpoint="https://search.example.com",
        credential=credential,
        knowledge_base_name="onboarding knowledge",
        api_version=ApiVersion.V2026_08_01_PREVIEW,
        connection_timeout=120,
        read_timeout=120,
        retry_total=0,
    )
    return retriever, credential, transport


def test_iq_retrieval_preserves_all_source_text_and_raw_response(iq_version):
    async def run():
        raw = {
            "response": [
                {"content": [{"text": "Answer [ref_id:7] [ref_id:9] [ref_id:10]"}]}
            ],
            "references": [
                {
                    "id": "7",
                    "sourceData": {"title": "Used.md", "chunk": "Cited evidence"},
                },
                {
                    "id": "8",
                    "sourceData": {
                        "title": "Also.md",
                        "chunk": "Other retrieved evidence",
                    },
                },
                {"id": "9", "sourceData": None},
                {
                    "id": "10",
                    "sourceData": {"title": "Long.md", "chunk": "Full text\n" * 1000},
                },
            ],
            "activity": [{"type": "searchIndex", "count": 2}],
            "additionalMetadata": {"preserved": True},
        }
        retriever, credential, transport = iq_retriever(iq_version, raw)
        try:
            result = await retriever.retrieve("Question")
        finally:
            await retriever.close()
        assert result == {
            "query": "Question",
            "answer": "Answer [ref_id:7] [ref_id:9] [ref_id:10]",
            "sources": [
                {"ref_id": "7", "title": "Used.md", "content": "Cited evidence"},
                {
                    "ref_id": "8",
                    "title": "Also.md",
                    "content": "Other retrieved evidence",
                },
                {"ref_id": "10", "title": "Long.md", "content": "Full text\n" * 1000},
            ],
            "raw_response": raw,
        }
        transport.send.assert_awaited_once()
        request = transport.send.call_args.args[0]
        assert request.method == "POST"
        assert request.url == (
            "https://search.example.com/knowledgebases('onboarding%20knowledge')"
            "/retrieve?api-version=2026-08-01-preview"
        )
        assert request.headers["Authorization"] == "Bearer test-token"
        assert json.loads(request.content) == {
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "Question"}]}
            ],
            "retrievalReasoningEffort": {"kind": "low"},
            "knowledgeSourceParams": [
                {
                    "knowledgeSourceName": "source",
                    "kind": "searchIndex",
                    "includeReferences": True,
                    "includeReferenceSourceData": True,
                }
            ],
        }
        credential.get_token.assert_awaited_once_with(
            "https://search.azure.com/.default"
        )
        transport.__aexit__.assert_awaited_once()
        credential.close.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"response": [], "references": []},
        {"response": [{"content": []}], "references": []},
        {"response": [{"content": [{"text": 7}]}], "references": []},
        {"response": [{"content": [{"text": "Answer"}]}], "references": None},
        *[
            {
                "response": [{"content": [{"text": "Answer [ref_id:7]"}]}],
                "references": [{"id": "7", "sourceData": source}],
            }
            for source in (
                {},
                {"title": "Title"},
                {"title": 7, "chunk": "Text"},
                {"title": "Title", "chunk": 7},
            )
        ],
    ],
)
def test_iq_retrieval_rejects_malformed_response(iq_version, payload):
    async def run():
        retriever, _, _ = iq_retriever(iq_version, payload)
        try:
            with pytest.raises(ValueError, match="Foundry IQ"):
                await retriever.retrieve("Question")
        finally:
            await retriever.close()

    asyncio.run(run())


@pytest.mark.parametrize("status_code", [401, 403, 429, 500])
def test_iq_http_errors_propagate_without_retry(iq_version, status_code):
    async def run():
        retriever, _, transport = iq_retriever(
            iq_version,
            {"error": {"code": "Injected", "message": "Retrieval failed"}},
            status_code=status_code,
        )
        try:
            with pytest.raises(HttpResponseError) as error:
                await retriever.retrieve("Question")
            assert error.value.status_code == status_code
            transport.send.assert_awaited_once()
        finally:
            await retriever.close()

    asyncio.run(run())


def test_iq_auth_errors_propagate(iq_version):
    async def run():
        retriever, credential, transport = iq_retriever(iq_version, {})
        credential.get_token.side_effect = ClientAuthenticationError(
            "Authentication failed"
        )
        try:
            with pytest.raises(ClientAuthenticationError, match="Authentication"):
                await retriever.retrieve("Question")
            transport.send.assert_not_awaited()
        finally:
            await retriever.close()

    asyncio.run(run())


@pytest.mark.parametrize("query", ["", " \n\t"])
def test_iq_empty_query_does_not_authenticate_or_retrieve(iq_version, query):
    async def run():
        retriever, credential, transport = iq_retriever(iq_version, {})
        try:
            with pytest.raises(ValueError, match="non-empty"):
                await retriever.retrieve(query)
            credential.get_token.assert_not_awaited()
            transport.send.assert_not_awaited()
        finally:
            await retriever.close()

    asyncio.run(run())


@pytest.mark.parametrize("answer", ["No evidence", "Unresolved [ref_id:99]"])
def test_iq_retrieval_preserves_sources_without_matching_citations(iq_version, answer):
    async def run():
        raw = {
            "response": [{"content": [{"text": answer}]}],
            "references": [
                {"id": "7", "sourceData": {"title": "Unused.md", "chunk": "Text"}}
            ],
        }
        retriever, _, _ = iq_retriever(iq_version, raw)
        try:
            result = await retriever.retrieve("Question")
            assert result == {
                "query": "Question",
                "answer": answer,
                "sources": [
                    {"ref_id": "7", "title": "Unused.md", "content": "Text"}
                ],
                "raw_response": raw,
            }
        finally:
            await retriever.close()

    asyncio.run(run())


def test_isolated_deployments_use_identical_v2_core():
    directory = Path(__file__).resolve().parents[1] / "src"
    shared_modules = {
        "rag_agent.py",
        "review_agent.py",
        "retrieval.py",
        "streaming.py",
    }
    for name in shared_modules:
        assert (directory / name).read_bytes() == (
            directory.parent.parent / "agent_v3" / "src" / name
        ).read_bytes()
    for version in ("agent_v1", "agent_v2", "agent_v3"):
        sources = directory.parent.parent / version / "src"
        expected = {"main.py"}
        if version != "agent_v1":
            expected |= shared_modules
        if version == "agent_v3":
            expected.add("memory.py")
        assert {path.name for path in sources.glob("*.py")} == expected
        assert not list(sources.rglob("test_*.py"))
        assert (sources.parent / "tests" / "test_main.py").is_file()
        tree = ast.parse((sources / "main.py").read_text(encoding="utf-8"))
        assert not any(isinstance(node, ast.ClassDef) for node in tree.body)
        assert [
            node.name for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
        ] == ["main"]
        assert not any(isinstance(node, ast.FunctionDef) for node in tree.body)
        assert not any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in {"create_agent", "create_workflow"}
            for node in ast.walk(tree)
        )


@pytest.mark.parametrize("server_fails", [False, True])
def test_main_constructs_agent_and_cleans_up_connections(version, server_fails):
    async def run():
        main, _ = version
        client = ScriptedChatClient()
        client.client = SimpleNamespace(close=AsyncMock())
        retriever = FakeRetriever()
        retriever.close = AsyncMock()
        credential, project = MagicMock(), MagicMock()
        project.__aenter__.return_value = project
        project.get_openai_client.return_value = MagicMock()
        with (
            patch.dict(
                "os.environ",
                {
                    "FOUNDRY_PROJECT_ENDPOINT": "https://example.test/api/projects/test",
                    "AZURE_AI_MODEL_DEPLOYMENT_NAME": "model",
                    "AZURE_SEARCH_ENDPOINT": "https://search.example.test",
                    "FOUNDRY_MEMORY_STORE_NAME": "memory",
                    "MAX_REVISIONS": "1",
                },
            ),
            patch("sys.argv", ["main.py"]),
            patch.object(main, "DefaultAzureCredential", return_value=credential),
            patch.object(main, "AIProjectClient", return_value=project),
            patch.object(main, "FoundryChatClient", return_value=client),
            patch.object(main, "FoundryIQRetriever", return_value=retriever),
            patch.object(main, "ResponsesHostServer") as server,
        ):
            server.return_value.run_async = AsyncMock(
                side_effect=RuntimeError("Server failed") if server_fails else None
            )
            if server_fails:
                with pytest.raises(RuntimeError, match="Server failed"):
                    await main.main()
            else:
                await main.main()
            agent = server.call_args.args[0]
            assert isinstance(agent, WorkflowAgent)
            version_name = main.__name__.split(".")[1]
            assert agent.name == f"onboarding_{version_name}"
            assert agent.workflow.name == f"onboarding_{version_name}_workflow"
            assert "history_source" not in server.call_args.kwargs
            finalizer = agent.workflow.executors["finalize_agent"].agent
            assert finalizer.default_options["store"] is False
            assert "max_tokens" not in finalizer.default_options
            if version_name == "agent_v3":
                assert (
                    finalizer.default_options["instructions"]
                    == main.MEMORY_FINALIZE_INSTRUCTIONS
                )
                assert isinstance(
                    finalizer.context_providers[-1], main.OnboardingMemoryProvider
                )
            else:
                assert finalizer.default_options["instructions"] == FINALIZE_INSTRUCTIONS
                assert len(finalizer.context_providers) == 1
        retriever.close.assert_awaited_once()
        client.client.close.assert_awaited_once()
        credential.__aexit__.assert_awaited_once()
        project.__aexit__.assert_awaited_once()

    asyncio.run(run())


@pytest.mark.parametrize("streaming", [False, True])
def test_host_returns_only_final_text_without_persisting_test_data(streaming):
    from agent_framework_foundry_hosting import ResponsesHostServer
    from azure.ai.agentserver.responses import InMemoryResponseProvider

    async def run():
        agent = await build(
            application,
            ScriptedChatClient(1),
            FakeRetriever(),
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
                json={"input": "Question", "stream": streaming, "store": False},
            )
            assert response.status_code == 200, response.text
            if streaming:
                events = [
                    json.loads(line.removeprefix("data: "))
                    for line in response.text.splitlines()
                    if line.startswith("data: {")
                ]
                assert not any(
                    event["type"] in ("response.failed", "error") for event in events
                )
                body = next(
                    event["response"]
                    for event in events
                    if event["type"] == "response.completed"
                )
            else:
                body = response.json()
            assert body["status"] == "completed", body
            text = "".join(
                content["text"]
                for item in body["output"]
                if item["type"] == "message"
                for content in item["content"]
                if content["type"] == "output_text"
            )
            assert text == "FINAL: Question"

    asyncio.run(run())
