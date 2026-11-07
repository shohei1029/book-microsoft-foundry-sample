import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from export_trace import REQUIRED_COLUMNS, export_csv, main


class TraceExportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name) / "trace.csv"
        self.columns = sorted(REQUIRED_COLUMNS)
        self.row = ['line1\nline2, "quoted" 日本語' for _ in self.columns]
        self.result = {"tables": [{"columns": [{"name": key} for key in self.columns], "rows": [self.row]}]}

    def test_default_query_resolves_within_the_chapter(self):
        with patch(
            "export_trace.argparse.ArgumentParser.parse_args", autospec=True, side_effect=SystemExit
        ) as parse_args:
            with self.assertRaises(SystemExit):
                main()
        query = parse_args.call_args.args[0].get_default("query")
        self.assertEqual(query, Path(__file__).resolve().parents[1] / "kql/export-stage-inputs.kql")
        self.assertEqual(query.read_text(encoding="utf-8").count("<TRACE_ID>"), 1)

    def test_csv_round_trip_preserves_long_json_and_unicode(self):
        self.assertEqual(export_csv(self.result, self.output), 1)
        with self.output.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows, [self.columns, self.row])

    def test_missing_empty_and_partial_results_fail(self):
        for result in [
            {"tables": []},
            {"tables": [{"columns": [], "rows": []}]},
            {"tables": [{"columns": self.result["tables"][0]["columns"], "rows": []}]},
            {"error": {"code": "PartialError"}, **self.result},
        ]:
            with self.subTest(result=result):
                with self.assertRaises(ValueError):
                    export_csv(result, self.output)
                self.assertFalse(self.output.exists())

    def test_existing_output_is_not_replaced(self):
        self.output.write_text("existing")
        with self.assertRaises(FileExistsError):
            export_csv(self.result, self.output)
        self.assertEqual(self.output.read_text(), "existing")


if __name__ == "__main__":
    unittest.main()
