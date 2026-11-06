"""Sample 19: deploy bundled source with the Foundry Python SDK."""

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


def build_bundled_zip(source_dir: Path, packages_dir: Path, zip_path: Path) -> str:
    source_files = {
        source_dir / "main.py",
        source_dir / "pyproject.toml",
        source_dir / "uv.lock",
        source_dir / "uv.toml",
    }
    required = {*source_files, packages_dir}
    missing = sorted(path.name for path in required if not path.exists())
    if missing:
        raise FileNotFoundError(f"Missing bundled inputs: {', '.join(missing)}")
    if not any(path.is_file() for path in packages_dir.rglob("*")):
        raise ValueError("packages_dir must contain extracted Python dependencies.")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_files):
            archive.write(path, path.name)
        for path in sorted(packages_dir.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, Path("packages") / path.relative_to(packages_dir))
    return hashlib.sha256(zip_path.read_bytes()).hexdigest()


def parse_args():
    check_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Validate inputs and definition only.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--project-endpoint", default=PROJECT_ENDPOINT)
    parser.add_argument("--agent-name", default="hosted-agent-sdk-bundled")
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--packages-dir", type=Path)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--poll-interval", type=float, default=5)
    parser.add_argument(
        "--prompt",
        default="オンボーディングのチェックリストを1文で説明してください。",
    )
    args = parser.parse_args()
    if not args.offline and args.packages_dir is None:
        parser.error("--packages-dir is required unless --offline is used.")
    return args


def main():
    args = parse_args()
    definition = HostedAgentDefinition(
        cpu="0.5",
        memory="1Gi",
        code_configuration=CodeConfiguration(
            runtime="python_3_13",
            entry_point=["python", "main.py"],
            dependency_resolution="bundled",
        ),
        protocol_versions=[
            ProtocolVersionRecord(protocol="responses", version="2.0.0")
        ],
        environment_variables={"AZURE_AI_MODEL_DEPLOYMENT_NAME": args.model},
    )
    with TemporaryDirectory(prefix="hosted-agent-sdk-bundled-") as temp_dir:
        packages_dir = args.packages_dir
        if packages_dir is None:
            packages_dir = Path(temp_dir) / "packages"
            packages_dir.mkdir()
            (packages_dir / "offline_fixture.py").write_text(
                "VALUE = 'offline fixture'\n",
                encoding="utf-8",
            )
        zip_path = Path(temp_dir) / "agent-code.zip"
        code_zip_sha256 = build_bundled_zip(
            args.source_dir,
            packages_dir,
            zip_path,
        )
        if args.offline:
            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
                assert "main.py" in names
                assert "pyproject.toml" in names
                assert "uv.lock" in names
                assert any(name.startswith("packages/") for name in names)
            assert definition.code_configuration is not None
            assert definition.code_configuration.dependency_resolution == "bundled"
            print(f"PASS: bundled zip ({code_zip_sha256}) and HostedAgentDefinition")
            return

        with (
            DefaultAzureCredential() as credential,
            AIProjectClient(
                endpoint=args.project_endpoint,
                credential=credential,
                allow_preview=True,
            ) as project,
        ):
            # %% SAMPLE START: deploy-sdk-bundled - Python SDK bundled deployment
            with zip_path.open("rb") as code:
                created = project.agents.create_version_from_code(
                    agent_name=args.agent_name,
                    definition=definition,
                    code=code,
                    code_zip_sha256=code_zip_sha256,
                    description="Python SDK bundled source-code deployment sample",
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
