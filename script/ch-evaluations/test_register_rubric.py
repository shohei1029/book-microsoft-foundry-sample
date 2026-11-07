import json
import tempfile
import unittest
from pathlib import Path

from register_rubric import load_definition


class RubricTests(unittest.TestCase):
    def test_original_criteria_and_threshold_are_preserved(self):
        path = Path(__file__).resolve().parents[2] / "data/ch-evaluations/rubric.json"
        original = json.loads(path.read_text())
        registered = load_definition(path, "new-evaluator")
        self.assertEqual(registered["dimensions"], original["dimensions"])
        self.assertEqual(registered["pass_threshold"], 0.75)
        self.assertEqual(len(registered["dimensions"]), 7)
        self.assertEqual(list(registered["metrics"]), ["new-evaluator"])
        self.assertEqual(json.loads(path.read_text()), original)

    def test_invalid_definition_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rubric.json"
            for value in [
                {"type": "code"},
                {"type": "rubric", "dimensions": []},
                {"type": "rubric", "dimensions": [{"id": "a"}, {"id": "a"}]},
            ]:
                path.write_text(json.dumps(value))
                with self.subTest(value=value), self.assertRaises(ValueError):
                    load_definition(path, "new-evaluator")


if __name__ == "__main__":
    unittest.main()
