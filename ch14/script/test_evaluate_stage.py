import csv
import json
import tempfile
import unittest
from pathlib import Path

from evaluate_stage import definition, load_record, prepare, submit, text_parts, write_new


def messages(text):
    return json.dumps([{"role": "user", "parts": [{"type": "text", "content": text}]}], ensure_ascii=False)


class StageEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.csv = self.root / "trace.csv"
        self.review = {"needs_revision": False, "feedback": "", "answer": "回答", "revision_count": 0}
        self.payload = {"question": "質問", "retrievals": [{"sources": [{"title": "資料", "content": "根拠"}]}]}
        self.row = {
            "operation_Id": "trace-1", "id": "span-1", "operation_ParentId": "parent-1",
            "contentId": "content-1", "stage": "review_agent", "agentName": "onboarding-agent-v3",
            "agentVersion": "2",
            "instructions": json.dumps([{"type": "text", "content": "完全な指示"}]),
            "inputMessages": messages(json.dumps(self.payload, ensure_ascii=False)),
            "outputMessages": messages(json.dumps(self.review, ensure_ascii=False)),
        }

    def write_csv(self, rows):
        with self.csv.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(self.row))
            writer.writeheader()
            writer.writerows(rows)

    def test_preserves_full_inputs_and_actual_output(self):
        self.write_csv([self.row])
        record = prepare(self.csv, "trace-1", "review_agent", None)
        self.assertIn(self.row["inputMessages"], record["query"])
        self.assertIn("完全な指示", record["query"])
        self.assertEqual(json.loads(record["response"]), self.review)
        self.assertEqual(record["span_id"], "span-1")
        self.assertEqual(record["revision_count"], 0)
        self.assertEqual(record["payload_source"], "genAIContent")

    def test_revision_loop_requires_explicit_span(self):
        self.write_csv([self.row, {**self.row, "id": "span-2"}])
        with self.assertRaises(ValueError):
            prepare(self.csv, "trace-1", "review_agent", None)
        self.assertEqual(prepare(self.csv, "trace-1", "review_agent", "span-2")["span_id"], "span-2")

    def test_large_full_payload_is_not_truncated_by_csv_reader(self):
        payload = {**self.payload, "retrievals": [{"sources": [{"title": "資料", "content": "根拠" * 100000}]}]}
        row = {**self.row, "inputMessages": messages(json.dumps(payload, ensure_ascii=False))}
        self.write_csv([row])
        record = prepare(self.csv, "trace-1", "review_agent", None)
        self.assertIn(row["inputMessages"], record["query"])

    def test_rejects_missing_or_truncated_evidence(self):
        for changes in [
            {"contentId": ""},
            {"inputMessages": self.row["inputMessages"][:30]},
            {"outputMessages": messages("{}")},
            {"inputMessages": messages('{"retrievals": []}')},
        ]:
            with self.subTest(changes=changes):
                self.write_csv([{**self.row, **changes}])
                with self.assertRaises(ValueError):
                    prepare(self.csv, "trace-1", "review_agent", None)

    def test_non_text_payload_is_explicitly_unsupported(self):
        with self.assertRaises(ValueError):
            text_parts([{"role": "user", "parts": [{"type": "image", "content": "image"}]}], "input")

    def test_reasoning_is_not_used_as_the_actual_response(self):
        output = [{"role": "assistant", "parts": [
            {"type": "reasoning", "content": "not the final response"},
            {"type": "text", "content": "actual response"},
        ]}]
        self.assertEqual(text_parts(output, "output", allow_reasoning=True), "actual response")
        with self.assertRaises(ValueError):
            text_parts(output, "input")

    def test_existing_output_is_preserved(self):
        output = self.root / "record.jsonl"
        write_new(output, {"value": 1})
        with self.assertRaises(FileExistsError):
            write_new(output, {"value": 2})
        self.assertEqual(json.loads(output.read_text())["value"], 1)

    def test_submit_requires_explicit_cost_confirmation_before_io(self):
        with self.assertRaisesRegex(ValueError, "confirm-cost"):
            submit(self.root / "missing.jsonl", self.root / "state.json", False)
        self.assertFalse((self.root / "state.json").exists())

    def test_single_record_and_stage_criteria(self):
        self.write_csv([self.row])
        record = prepare(self.csv, "trace-1", "review_agent", None)
        output = self.root / "record.jsonl"
        write_new(output, record)
        self.assertEqual(load_record(output), record)
        rubric = definition("review_agent")
        self.assertEqual(rubric["pass_threshold"], 0.6)
        self.assertEqual([dimension["weight"] for dimension in rubric["dimensions"]], [9, 2])


if __name__ == "__main__":
    unittest.main()
