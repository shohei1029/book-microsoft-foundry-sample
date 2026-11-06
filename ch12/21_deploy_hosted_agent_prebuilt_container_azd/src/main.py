import asyncio
import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework.openai import OpenAIChatOptions
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity.aio import DefaultAzureCredential


async def main() -> None:
    credential = DefaultAzureCredential()
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )
    agent = Agent[OpenAIChatOptions](
        client=client,
        instructions="You are a concise onboarding assistant.",
        default_options={"store": False},
    )
    try:
        await ResponsesHostServer(agent).run_async()
    finally:
        await client.client.close()
        await client.project_client.close()
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
