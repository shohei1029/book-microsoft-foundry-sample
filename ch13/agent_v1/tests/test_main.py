import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import (
    Agent,
    BaseChatClient,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    InMemoryHistoryProvider,
    Message,
    ResponseStream,
)
from agent_framework_foundry_hosting import ResponsesHostServer

from apps.agent_v1.src import main as application
from apps.agent_v1.src.main import (
    FINALIZE_INSTRUCTIONS,
    REVIEW_INSTRUCTIONS,
)


class ScriptedChatClient(BaseChatClient):
    def __init__(self):
        super().__init__()
        self.calls = []

    def _inner_get_response(self, *, messages, stream, options, **kwargs):
        instructions = options["instructions"]
        self.calls.append((instructions, list(messages)))
        replies = {
            "SEARCH": "DRAFT: supported fact",
            REVIEW_INSTRUCTIONS: "REVIEW: supported fact",
            FINALIZE_INSTRUCTIONS: "FINAL: supported fact",
        }
        response = ChatResponse(
            messages=[
                Message(
                    role="assistant",
                    contents=[Content.from_text(replies[instructions])],
                )
            ]
        )

        async def respond():
            return response

        if stream:

            async def updates():
                yield ChatResponseUpdate(
                    role="assistant", contents=response.messages[0].contents
                )

            return ResponseStream(updates(), finalizer=ChatResponse.from_updates)
        return respond()


@pytest.mark.parametrize("streaming", [False, True])
def test_existing_prompt_agent_runs_before_review_and_finalize(streaming):
    async def run():
        client = ScriptedChatClient()
        search_agent = Agent(
            name="existing_prompt_agent",
            client=client,
            instructions="SEARCH",
            context_providers=[
                InMemoryHistoryProvider(store_inputs=False, store_outputs=False)
            ],
            default_options={"store": False},
        )
        client.client = SimpleNamespace(close=AsyncMock())
        project = MagicMock()
        project.__aenter__.return_value = project
        project.get_openai_client.return_value = MagicMock()
        results = []

        async def serve():
            agent = server.call_args.args[0]
            first = agent.run("First question", stream=streaming)
            if streaming:
                updates = [update async for update in first]
                assert (
                    "".join(update.text for update in updates)
                    == "FINAL: supported fact"
                )
                first = await first.get_final_response()
            else:
                first = await first
            results.extend([first, await agent.run("Second question")])

        with (
            patch.dict(
                "os.environ",
                {
                    "FOUNDRY_PROJECT_ENDPOINT": "https://example.test/api/projects/test",
                    "AZURE_AI_MODEL_DEPLOYMENT_NAME": "test-model",
                },
            ),
            patch.object(
                application, "DefaultAzureCredential", return_value=MagicMock()
            ),
            patch.object(application, "AIProjectClient", return_value=project),
            patch.object(application, "FoundryAgent", return_value=search_agent),
            patch.object(application, "FoundryChatClient", return_value=client),
            patch.object(application, "ResponsesHostServer") as server,
        ):
            server.return_value.run_async = AsyncMock(side_effect=serve)
            await application.main()
        first, second = results
        client.client.close.assert_awaited_once()

        assert first.text == "FINAL: supported fact"
        assert second.text == "FINAL: supported fact"
        assert [instructions for instructions, _ in client.calls] == [
            "SEARCH",
            REVIEW_INSTRUCTIONS,
            FINALIZE_INSTRUCTIONS,
            "SEARCH",
            REVIEW_INSTRUCTIONS,
            FINALIZE_INSTRUCTIONS,
        ]
        for _, messages in client.calls[3:]:
            assert all("First question" not in message.text for message in messages)

    asyncio.run(run())


def test_custom_agent_uses_agent_managed_history():
    async def run():
        client = ScriptedChatClient()
        client.client = SimpleNamespace(close=AsyncMock())
        project = MagicMock()
        project.__aenter__.return_value = project
        project.get_openai_client.return_value = MagicMock()
        search_agent = Agent(
            name="existing_prompt_agent",
            client=client,
            instructions="SEARCH",
            context_providers=[
                InMemoryHistoryProvider(store_inputs=False, store_outputs=False)
            ],
            default_options={"store": False},
        )
        with (
            patch.dict(
                "os.environ",
                {
                    "FOUNDRY_PROJECT_ENDPOINT": "https://example.test/api/projects/test",
                    "AZURE_AI_MODEL_DEPLOYMENT_NAME": "test-model",
                },
            ),
            patch.object(
                application, "DefaultAzureCredential", return_value=MagicMock()
            ),
            patch.object(application, "AIProjectClient", return_value=project),
            patch.object(application, "FoundryAgent", return_value=search_agent),
            patch.object(application, "FoundryChatClient", return_value=client),
            patch.object(ResponsesHostServer, "run_async", new_callable=AsyncMock),
        ):
            await application.main()

    asyncio.run(run())
