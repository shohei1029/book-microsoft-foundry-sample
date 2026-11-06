import asyncio
import os

from agent_framework import Agent, ChatOptions, InMemoryHistoryProvider, WorkflowBuilder
from agent_framework.foundry import FoundryAgent, FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential

REVIEW_INSTRUCTIONS = """
あなたは社内オンボーディングの回答案を確認するレビュー担当です。
RAGエージェントの回答案に含まれる根拠、引用、留保を確認してください。
元資料の本文は共有されていないため、独立に検証したとは主張しないでください。
内部矛盾、根拠のない断定、引用と主張の不一致を削除または修正し、
確認できない点は留保してください。自分の知識で事実や参照先を追加しないでください。
「修正点と理由」「修正済み回答」を日本語で出力してください。
""".strip()

FINALIZE_INSTRUCTIONS = """
あなたはレビュー結果をユーザー向けの最終回答に整える担当です。
レビュー担当の修正済み回答を基に、ユーザーが求める粒度で日本語で回答してください。
削除・否定された主張を復活させず、新しい事実や参照先を追加しないでください。
根拠不足についての留保と、レビューで残された文書タイトルを保持してください。
回答案、レビュー過程、エージェント名は表示しないでください。
""".strip()


async def main() -> None:
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            credential=credential,
        ) as project,
    ):
        search_agent = FoundryAgent(
            project_client=project,
            agent_name=os.environ.get(
                "FOUNDRY_SEARCH_AGENT_NAME", "onbording-search-agent"
            ),
            agent_version=os.environ.get("FOUNDRY_SEARCH_AGENT_VERSION", "2"),
            context_providers=[
                InMemoryHistoryProvider(store_inputs=False, store_outputs=False)
            ],
            default_options={"store": False},
        )
        client = FoundryChatClient(
            project_client=project,
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        )
        try:
            async with search_agent:
                review_agent = Agent[ChatOptions](
                    name="review_agent",
                    client=client,
                    instructions=REVIEW_INSTRUCTIONS,
                    context_providers=[
                        InMemoryHistoryProvider(store_inputs=False, store_outputs=False)
                    ],
                    default_options={"store": False},
                )
                finalize_agent = Agent[ChatOptions](
                    name="finalize_agent",
                    client=client,
                    instructions=FINALIZE_INSTRUCTIONS,
                    context_providers=[
                        InMemoryHistoryProvider(store_inputs=False, store_outputs=False)
                    ],
                    default_options={"store": False},
                )

                workflow = (
                    WorkflowBuilder(
                        name="onboarding_v1_workflow",
                        start_executor=search_agent,
                        output_from=[finalize_agent],
                    )
                    .add_edge(search_agent, review_agent)
                    .add_edge(review_agent, finalize_agent)
                    .build()
                )
                server = ResponsesHostServer(
                    workflow.as_agent(name="onboarding_agent_v1")
                )
                await server.run_async()
        finally:
            await client.client.close()


if __name__ == "__main__":
    asyncio.run(main())
