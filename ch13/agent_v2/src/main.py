import asyncio
import os

from agent_framework import (
    Agent,
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentSession,
    ChatOptions,
    InMemoryHistoryProvider,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    executor,
)
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential

if __package__:
    from .rag_agent import RagAgent
    from .retrieval import FoundryIQRetriever
    from .review_agent import ReviewAgent, ReviewResult
else:
    from rag_agent import RagAgent
    from retrieval import FoundryIQRetriever
    from review_agent import ReviewAgent, ReviewResult


FINALIZE_INSTRUCTIONS = """
レビュー結果のanswerを基に、元の質問に合う粒度で日本語の最終回答を整えてください。
新しい事実や参照先を加えず、文書タイトルと不確実性の留保を保持してください。
needs_revisionがtrueのままなら修正上限に到達しています。feedbackの未解決事項を
断定で埋めず、確認できない点として残してください。
JSONの管理項目、回数、内部ID、草案、レビュー過程やエージェント名は出力しないでください。
""".strip()


async def main() -> None:
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            credential=credential,
        ) as project,
    ):
        retriever = FoundryIQRetriever(
            credential=credential,
            endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
            knowledge_base_name=os.environ.get(
                "FOUNDRY_IQ_KNOWLEDGE_BASE_NAME", "onboarding-knowledgebase"
            ),
            knowledge_source_name=os.environ.get(
                "FOUNDRY_IQ_KNOWLEDGE_SOURCE_NAME", "onbording-knowledgesource"
            ),
        )
        client = FoundryChatClient(
            project_client=project,
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        )
        try:
            max_revisions = int(os.environ.get("MAX_REVISIONS", "2"))
            if max_revisions < 0:
                raise ValueError("MAX_REVISIONS must be a non-negative integer.")
            session = AgentSession()

            @executor(id="prepare_request")
            async def prepare_request(
                messages: list[Message],
                ctx: WorkflowContext[AgentExecutorRequest],
            ) -> None:
                question = next(
                    (
                        message.text
                        for message in reversed(messages)
                        if message.role == "user" and message.text.strip()
                    ),
                    None,
                )
                if question is None:
                    raise ValueError("Onboarding requires a non-empty user question.")
                session.state["onboarding"] = {
                    "question": question,
                    "user_input": [message.to_dict() for message in messages],
                    "retrievals": [],
                    "draft": None,
                    "review": None,
                    "revision_count": 0,
                }
                await ctx.send_message(AgentExecutorRequest(messages))

            rag = AgentExecutor(RagAgent(client, retriever), session=session)
            review = AgentExecutor(ReviewAgent(client), session=session)

            def final_context(conversation: list[Message]) -> list[Message]:
                question = next(
                    message
                    for message in conversation
                    if message.role == "user"
                    and not message.additional_properties.get("_attribution")
                )
                return [question, conversation[-1]]

            finalize = AgentExecutor(
                Agent[ChatOptions](
                    name="finalize_agent",
                    client=client,
                    instructions=FINALIZE_INSTRUCTIONS,
                    context_providers=[
                        InMemoryHistoryProvider(store_inputs=False, store_outputs=False),
                    ],
                    default_options={"store": False},
                ),
                session=session,
                context_mode="custom",
                context_filter=final_context,
            )

            def should_revise(response: AgentExecutorResponse) -> bool:
                result = response.agent_response.value
                if not isinstance(result, ReviewResult):
                    raise TypeError("ReviewAgent must return a ReviewResult.")
                return result.needs_revision and result.revision_count < max_revisions

            workflow = (
                WorkflowBuilder(
                    name="onboarding_agent_v2_workflow",
                    start_executor=prepare_request,
                    output_from=[finalize],
                    intermediate_output_from=[],
                    max_iterations=2 * max_revisions + 6,
                )
                .add_edge(prepare_request, rag)
                .add_edge(rag, review)
                .add_edge(review, rag, condition=should_revise)
                .add_edge(
                    review,
                    finalize,
                    condition=lambda response: not should_revise(response),
                )
                .build()
            )
            server = ResponsesHostServer(
                workflow.as_agent(name="onboarding_agent_v2")
            )
            await server.run_async()
        finally:
            await retriever.close()
            await client.client.close()


if __name__ == "__main__":
    asyncio.run(main())
