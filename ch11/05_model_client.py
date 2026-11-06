"""Sample 4: create a Foundry model client with Microsoft Entra authentication."""

import asyncio

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework.openai import OpenAIChatOptions
from azure.identity import DefaultAzureCredential

from sample_support import PROJECT_ENDPOINT, parse_args


async def main():
    args = parse_args(__doc__)
    credential = DefaultAzureCredential()

    # %% SAMPLE START: 5 - Foundry model client
    client = FoundryChatClient(
        project_endpoint=PROJECT_ENDPOINT,
        model=args.model,
        credential=credential,
    )
    # %% SAMPLE END

    try:
        assert client.model == args.model
        if not args.offline:
            agent = Agent[OpenAIChatOptions](
                client=client,
                instructions="Reply with only the word ready.",
                default_options={"store": False},
            )
            response = await agent.run("Confirm that the model is available.")
            assert response.text.strip()
            print(response.text)
        print(f"PASS: FoundryChatClient configured for {PROJECT_ENDPOINT} ({args.model})")
    finally:
        await client.client.close()
        await client.project_client.close()
        credential.close()


if __name__ == "__main__":
    asyncio.run(main())
