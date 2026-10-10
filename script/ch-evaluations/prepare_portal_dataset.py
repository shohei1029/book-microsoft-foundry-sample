"""Separate agent input from the Portal's automatically mapped grading query."""

import argparse
import json
from pathlib import Path


def prepare(input_path: Path, output_path: Path) -> int:
    records = [
        json.loads(line)
        for line in input_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    if not records:
        raise ValueError("The input dataset is empty.")
    identifiers = set()
    questions = set()
    prepared = []
    for record in records:
        for field in ("case_id", "category", "test_type", "query", "expected_behavior"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError(f"Missing or empty string field: {field}")
        if record["case_id"] in identifiers or record["query"] in questions:
            raise ValueError("Duplicate case ID or agent question.")
        identifiers.add(record["case_id"])
        questions.add(record["query"])
        prepared.append(
            {
                "case_id": record["case_id"],
                "category": record["category"],
                "test_type": record["test_type"],
                "agent_query": record["query"],
                "query": (
                    "ORIGINAL USER QUESTION\n"
                    + record["query"]
                    + "\n\nEVALUATION-ONLY EXPECTED BEHAVIOR\n"
                    + record["expected_behavior"]
                ),
                "expected_behavior": record["expected_behavior"],
            }
        )
    with output_path.open("x", encoding="utf-8", newline="\n") as stream:
        for record in prepared:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(prepared)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    count = prepare(args.input, args.output)
    print(f"Prepared {count} rows. Agent input must be {{{{item.agent_query}}}}.")
    print("The evaluator query must be {{item.query}}. No cloud calls were made.")


if __name__ == "__main__":
    main()