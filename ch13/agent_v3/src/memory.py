import json

from agent_framework import ContextProvider, Message
from azure.ai.agentserver.core import get_request_context
from azure.ai.projects.aio import AIProjectClient


class OnboardingMemoryProvider(ContextProvider):
    def __init__(self, project: AIProjectClient, memory_store_name: str) -> None:
        super().__init__("foundry_memory")
        if not memory_store_name:
            raise ValueError("memory_store_name is required.")
        self.project = project
        self.memory_store_name = memory_store_name

    async def before_run(self, *, agent, session, context, state) -> None:
        request = get_request_context()
        if not request.user_id:
            raise ValueError(
                "Foundry Memory requires the platform-authenticated user identity."
            )
        question = session.state["onboarding"]["question"]
        context.metadata[self.source_id] = {
            "scope": request.user_id,
            "headers": request.platform_headers(),
            "question": question,
        }
        result = await self.project.beta.memory_stores.search_memories(
            name=self.memory_store_name,
            scope=request.user_id,
            items=[{"role": "user", "type": "message", "content": question}],
            headers=request.platform_headers(),
        )
        memories = [item.memory_item.content for item in result.memories]
        if memories:
            context.extend_messages(
                self,
                [
                    Message(
                        "user",
                        [
                            "Foundry Memory (personal context, not factual evidence):\n"
                            + json.dumps(memories, ensure_ascii=False)
                        ],
                    )
                ],
            )

    async def after_run(self, *, agent, session, context, state) -> None:
        if context.response is None or not context.response.text.strip():
            raise ValueError("Cannot save memory without a completed final response.")
        request = context.metadata[self.source_id]
        update = await self.project.beta.memory_stores.begin_update_memories(
            name=self.memory_store_name,
            scope=request["scope"],
            items=[
                {"role": "user", "type": "message", "content": request["question"]},
                {
                    "role": "assistant",
                    "type": "message",
                    "content": context.response.text,
                },
            ],
            update_delay=0,
            headers=request["headers"],
        )
        await update.result()
