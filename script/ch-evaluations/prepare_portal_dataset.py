import argparse
import json
from pathlib import Path


def grading_query(query: str, expected_behavior: str) -> str:
    return (
        f"ORIGINAL USER QUESTION\n{query}\n\n"
        f"EVALUATION-ONLY EXPECTED BEHAVIOR\n{expected_behavior}"
    )


def load_questions(path: Path) -> list[dict]:
    records = []
    identifiers = set()
    required = ("case_id", "category", "test_type", "query", "expected_behavior", "source")
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            raise ValueError(f"{path}:{number}: blank JSONL record.")
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError(f"{path}:{number}: expected a JSON object.")
        for field in required:
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError(f"{path}:{number}: missing or empty {field}.")
        if record["case_id"] in identifiers:
            raise ValueError(f"{path}:{number}: duplicate case_id.")
        identifiers.add(record["case_id"])
        expected_query = grading_query(record["query"], record["expected_behavior"])
        if "evaluation_query" in record and record["evaluation_query"] != expected_query:
            raise ValueError(f"{path}:{number}: evaluation_query does not match the source fields.")
        records.append(record)
    if not records:
        raise ValueError(f"{path}: no evaluation cases.")
    return records


def prepare(source: Path, output: Path, limit: int | None = None) -> int:
    records = load_questions(source)
    if limit is not None:
        if not 1 <= limit <= len(records):
            raise ValueError("--limit must be between 1 and the input case count.")
        records = records[:limit]
    converted = [
        {
            "case_id": record["case_id"],
            "category": record["category"],
            "test_type": record["test_type"],
            "agent_query": record["query"],
            "query": grading_query(record["query"], record["expected_behavior"]),
            "expected_behavior": record["expected_behavior"],
        }
        for record in records
    ]
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        for record in converted:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(converted)


def main() -> None:
    parser = argparse.ArgumentParser(description="Separate agent input from evaluation-only expectations.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, help="Prepare only the first N cases for a smoke test.")
    args = parser.parse_args()
    try:
        count = prepare(args.input, args.output, args.limit)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Dataset preparation failed: {error}\n")
    print(json.dumps({"output": str(args.output), "cases": count, "cloud_calls": 0}))


if __name__ == "__main__":
    main()
