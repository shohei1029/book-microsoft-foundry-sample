import json
import tempfile
import unittest
from pathlib import Path

from prepare_portal_dataset import grading_query, load_questions, prepare


class PortalDatasetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "source.jsonl"
        self.output = self.root / "portal.jsonl"
        self.record = {
            "case_id": "E001",
            "category": "expenses",
            "test_type": "factual",
            "query": "経費精算の確認者を教えてください。",
            "expected_behavior": "申請者、マネージャー、Financeの役割を区別する。",
            "source": "expenses.md#承認",
        }

    def write_records(self, records):
        self.source.write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
            encoding="utf-8",
        )

    def test_input_is_separated_from_grading_expectations(self):
        self.write_records([self.record])
        self.assertEqual(prepare(self.source, self.output), 1)
        result = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(result["agent_query"], self.record["query"])
        self.assertEqual(
            result["query"], grading_query(self.record["query"], self.record["expected_behavior"])
        )
        self.assertNotIn("source", result)
        self.assertNotIn("evaluation_query", result)

    def test_existing_output_is_not_overwritten(self):
        self.write_records([self.record])
        self.output.write_text("existing", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            prepare(self.source, self.output)
        self.assertEqual(self.output.read_text(), "existing")

    def test_invalid_inputs_are_rejected(self):
        for records in [
            [],
            [self.record, self.record],
            [{**self.record, "query": ""}],
            [{**self.record, "evaluation_query": "wrong"}],
            [None],
        ]:
            with self.subTest(records=records):
                self.write_records(records)
                with self.assertRaises(ValueError):
                    prepare(self.source, self.output)
                self.assertFalse(self.output.exists())

    def test_smoke_limit(self):
        self.write_records([self.record, {**self.record, "case_id": "E002"}])
        self.assertEqual(prepare(self.source, self.output, 1), 1)
        self.assertEqual(len(self.output.read_text().splitlines()), 1)
        for limit in (0, 3):
            with self.assertRaises(ValueError):
                prepare(self.source, self.root / f"limit-{limit}.jsonl", limit)

    def test_restored_dataset_has_100_source_backed_cases(self):
        source = Path(__file__).resolve().parents[1] / "data/questions.jsonl"
        records = load_questions(source)
        self.assertEqual(len(records), 100)
        self.assertEqual(len({record["category"] for record in records}), 10)
        self.assertEqual(len({record["source"].split("#")[0] for record in records}), 23)


if __name__ == "__main__":
    unittest.main()
