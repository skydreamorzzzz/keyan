import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MULTIBENCH_DIR = os.path.join(ROOT, "pilot", "multibench")
if MULTIBENCH_DIR not in sys.path:
    sys.path.insert(0, MULTIBENCH_DIR)

import tatqa_output_normalization_audit as audit  # noqa: E402


class TatqaOutputNormalizationAuditTest(unittest.TestCase):
    def canon(self, answer, scale=""):
        return audit.canonicalize_prediction({"answer": answer, "scale": scale})[0]

    def test_currency_million_duplicate_scale(self):
        self.assertEqual(self.canon("$46.4 million", "million"), {"answer": "46.4", "scale": "million"})

    def test_plain_number_with_million_scale_unchanged(self):
        self.assertEqual(self.canon("174.5", "million"), {"answer": "174.5", "scale": "million"})

    def test_percent_word_duplicate_scale(self):
        self.assertEqual(self.canon("23.4 percent", "percent"), {"answer": "23.4%", "scale": "percent"})

    def test_comma_number(self):
        self.assertEqual(self.canon("$1,496.5", "million"), {"answer": "1496.5", "scale": "million"})

    def test_text_span_preserved(self):
        pred = {"answer": "cash flow growth and investments in headcount", "scale": ""}
        self.assertEqual(audit.canonicalize_prediction(pred)[0], pred)

    def test_multi_span_text_preserved(self):
        pred = {"answer": ["Rate of inflation", "Discount rate"], "scale": ""}
        self.assertEqual(audit.canonicalize_prediction(pred)[0], pred)


if __name__ == "__main__":
    unittest.main()
