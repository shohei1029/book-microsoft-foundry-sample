"""Sample 17: deploy remote_build source with the Foundry Python SDK."""

import argparse
import hashlib
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    CodeConfiguration,
    HostedAgentDefinition,
    ProtocolVersionRecord,
)
from azure.identity import DefaultAzureCredential

from sample_support import DEFAULT_MODEL, PROJECT_ENDPOINT, check_environment


SOURCE_DIR = Path(__file__).with_name("hosted_agent_source")


def build_code_zip(source_dir: Path, zip_path: Path) -> str:
    required = {
        source_dir / "main.py",
        source_dir / "pyproject.toml",
        source_dir / "uv.lock",
        source_dir / "uv.toml",
    }
    missing = sorted(str(path.name) for path in required if not path.is_file())
    if missing:
        raise FileNotFoundError(f"Missing source files: {', '.join(missing)}")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(required):
            archive.write(path, path.name)
    return hashlib.sha256(zip_path.read_bytes()).hexdigest()


def parse_args():
    check_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Build and validate the code zip only.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--project-endpoint", default=PROJECT_ENDPOINT)
    parser.add_argument("--agent-name", default="hosted-agent-sdk-sample")
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--poll-interval", type=float, default=5)
    parser.add_argument(
        "--prompt",
        default="オンボーディングのチェックリストを1文で説明してください。",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    definition = HostedAgentDefinition(
        cpu="0.5",
        memory="1Gi",
        code_configuration=CodeConfiguration(
            runtime="python_3_13",
            entry_point=["python", "main.py"],
            dependency_resolution="remote_build",
        ),
        protocol_versions=[
            ProtocolVersionRecord(protocol="responses", version="2.0.0")
        ],
        environment_variables={"AZURE_AI_MODEL_DEPLOYMENT_NAME": args.model},
    )
    with TemporaryDirectory(prefix="hosted-agent-sdk-") as temp_dir:
        zip_path = Path(temp_dir) / "agent-code.zip"
        code_zip_sha256 = build_code_zip(args.source_dir, zip_path)
        if args.offline:
            with zipfile.ZipFile(zip_path) as archive:
                assert set(archive.namelist()) == {
                    "main.py",
                    "pyproject.toml",
                    "uv.lock",
                    "uv.toml",
                }
            assert definition.code_configuration is not None
            assert definition.code_configuration.dependency_resolution == "remote_build"
            print(f"PASS: source zip ({code_zip_sha256}) and HostedAgentDefinition")
            return

        with (
            DefaultAzureCredential() as credential,
            AIProjectClient(
                endpoint=args.project_endpoint,
                credential=credential,
                allow_preview=True,
            ) as project,
        ):
            # %% SAMPLE START: deploy-sdk-remote - Python SDK remote_build deployment
            with zip_path.open("rb") as code:
                created = project.agents.create_version_from_code(
                    agent_name=args.agent_name,
                    definition=definition,
                    code=code,
                    code_zip_sha256=code_zip_sha256,
                    description="Python SDK source-code deployment sample",
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
