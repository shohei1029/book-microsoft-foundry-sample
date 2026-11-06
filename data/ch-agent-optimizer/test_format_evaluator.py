import importlib.util
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "format_evaluator", Path(__file__).with_name("format-evaluator.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
GOOD = """## 結論
担当者へ確認します。
## 手順
1. 資料を確認します。
2. 担当者へ連絡します。
## 参照資料
問い合わせの案内
## 確認事項
担当者が不明な場合は窓口で確認します。
"""


class FormatEvaluatorTests(unittest.TestCase):
    def test_input_shapes(self):
        for sample, item in [
            ({}, {"response": GOOD}),
            ({}, {"sample": {"output_text": GOOD}}),
            ({}, {"sample.output_text": GOOD}),
            ({"output_text": GOOD}, {}),
        ]:
            with self.subTest(sample=sample, item=item):
                self.assertEqual(MODULE.grade(sample, item), 1.0)

    def test_supported_heading_styles(self):
        for text in [
            GOOD.replace("## ", ""),
            GOOD.replace("## ", "■"),
            GOOD.replace("## 結論", "**結論**").replace("## 手順", "**手順**")
                .replace("## 参照資料", "**参照資料**")
                .replace("## 確認事項", "**確認事項**"),
            GOOD.replace("\n", "\r\n"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(MODULE.grade({}, {"response": text}), 1.0)

    def test_step_count_boundaries(self):
        steps = "1. 資料を確認します。\n2. 担当者へ連絡します。"
        for count in range(5):
            text = GOOD.replace(
                steps, "\n".join(f"{number}. 確認します。" for number in range(1, count + 1))
            )
            with self.subTest(count=count):
                self.assertEqual(
                    MODULE.grade({}, {"response": text}), float(1 <= count <= 3)
                )

    def test_format_failures(self):
        for text in [
            "",
            GOOD.replace("## 結論", "## 回答"),
            GOOD.replace("## 確認事項", "## 補足"),
            GOOD.replace("## 結論", "## 手順", 1),
            GOOD.replace("担当者へ確認します。", ""),
            GOOD.replace("2. 担当者へ", "3. 担当者へ"),
            GOOD + "\n## 結論\n重複した見出しです。",
            "```\n" + GOOD + "```\n",
        ]:
            with self.subTest(text=text):
                self.assertEqual(MODULE.grade({}, {"response": text}), 0.0)

    def test_invalid_inputs_are_explicit_errors(self):
        with self.assertRaises(ValueError):
            MODULE.grade({}, {})
        with self.assertRaises(TypeError):
            MODULE.grade({}, {"response": None})


if __name__ == "__main__":
    unittest.main()
