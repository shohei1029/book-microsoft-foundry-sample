import argparse
import copy
import json
from pathlib import Path

from evaluate_stage import cloud_client, write_new


def load_definition(path: Path, name: str) -> dict:
    definition = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(definition, dict) or definition.get("type") != "rubric":
        raise ValueError("Expected a rubric evaluator definition.")
    dimensions = definition.get("dimensions", [])
    if (
        not isinstance(dimensions, list)
        or not dimensions
        or any(not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in dimensions)
        or len({item["id"] for item in dimensions}) != len(dimensions)
    ):
        raise ValueError("Rubric dimensions must be nonempty and have unique IDs.")
    if not 0 <= definition.get("pass_threshold", -1) <= 1:
        raise ValueError("The pass threshold must be between 0 and 1.")
    metrics = definition.get("metrics", {})
    if len(metrics) != 1:
        raise ValueError("This example requires exactly one aggregate metric.")
    definition["metrics"] = {name: copy.deepcopy(next(iter(metrics.values())))}
    return definition


def main():
    parser = argparse.ArgumentParser(description="Register a fixed rubric without LLM-based regeneration.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-create", action="store_true")
    args = parser.parse_args()
    try:
        if not args.confirm_create:
            raise ValueError("--confirm-create is required to create a cloud evaluator version.")
        definition = load_definition(args.input, args.name)
        state = {"phase": "creating", "name": args.name}
        write_new(args.output, state)
        with cloud_client() as project:
            evaluator = project.beta.evaluators.create_version(
                name=args.name,
                evaluator_version={
                    "display_name": args.display_name,
                    "categories": ["quality"],
                    "definition": definition,
                },
            )
            saved = project.beta.evaluators.get_version(name=args.name, version=evaluator.version)
            actual = saved.as_dict()
            if actual["definition"]["dimensions"] != definition["dimensions"]:
                raise ValueError("Saved rubric dimensions differ from the input; inspect the new version.")
            if actual["definition"]["pass_threshold"] != definition["pass_threshold"]:
                raise ValueError("Saved rubric threshold differs from the input.")
        state.update(phase="verified", version=evaluator.version, id=evaluator.id)
        args.output.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.exit(1, f"Rubric registration failed: {error}\n")
    print(json.dumps(state, ensure_ascii=False))


if __name__ == "__main__":
    main()
