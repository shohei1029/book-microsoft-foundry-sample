"""Sample 22: deploy a prebuilt container with the Foundry Python SDK.

Before running, push the image to ACR and grant the Foundry project's managed
identity AcrPull for a classic RBAC registry, or Container Registry Repository
Reader for an ABAC-enabled registry.
"""

import argparse
import time

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AgentEndpointProtocol,
    ContainerConfiguration,
    HostedAgentDefinition,
    ProtocolVersionRecord,
)
from azure.identity import DefaultAzureCredential

from sample_support import DEFAULT_MODEL, PROJECT_ENDPOINT, check_environment


def parse_args():
    check_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Validate the definition only.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--project-endpoint", default=PROJECT_ENDPOINT)
    parser.add_argument("--agent-name", default="hosted-agent-sdk-container")
    parser.add_argument("--image")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--poll-interval", type=float, default=5)
    parser.add_argument(
        "--prompt",
        default="オンボーディングのチェックリストを1文で説明してください。",
    )
    args = parser.parse_args()
    if args.image is None:
        if not args.offline:
            parser.error("--image is required unless --offline is used.")
        args.image = "example.azurecr.io/agents/offline-fixture:v1"
    return args


def main():
    args = parse_args()
    definition = HostedAgentDefinition(
        cpu="0.5",
        memory="1Gi",
        container_configuration=ContainerConfiguration(image=args.image),
        protocol_versions=[
            ProtocolVersionRecord(
                protocol=AgentEndpointProtocol.RESPONSES,
                version="2.0.0",
            )
        ],
        environment_variables={"AZURE_AI_MODEL_DEPLOYMENT_NAME": args.model},
    )
    if args.offline:
        assert definition.container_configuration is not None
        assert definition.container_configuration.image == args.image
        assert definition.code_configuration is None
        print("PASS: ContainerConfiguration and HostedAgentDefinition")
        return

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=args.project_endpoint,
            credential=credential,
            allow_preview=True,
        ) as project,
    ):
        # %% SAMPLE START: deploy-sdk-container - Python SDK container deployment
        created = project.agents.create_version(
            agent_name=args.agent_name,
            definition=definition,
            description="Python SDK prebuilt-container deployment sample",
        )

        deadline = time.monotonic() + args.timeout
        while True:
            version = project.agents.get_version(
                agent_name=args.agent_name,
                agent_version=created.version,
            )
            status = getattr(version.status, "value", version.status)
            if status == "active":
                break
            if status == "failed":
                raise RuntimeError(
                    f"Hosted Agent deployment failed: {version.as_dict().get('error')}"
                )
            if time.monotonic() >= deadline:
                raise TimeoutError("Hosted Agent deployment did not become active.")
            time.sleep(args.poll_interval)

        project.agents.enable(agent_name=args.agent_name)
        get_openai_client = getattr(project, "get_openai_client", None)
        if not callable(get_openai_client):
            raise RuntimeError("Installed azure-ai-projects does not provide an OpenAI client.")
        openai_client = get_openai_client(agent_name=args.agent_name)
        try:
            response = openai_client.responses.create(input=args.prompt)
        finally:
            openai_client.close()
        # %% SAMPLE END
        print(f"Agent: {args.agent_name}:{created.version}")
        print(response.output_text)


if __name__ == "__main__":
    main()
