import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MULTIBENCH_DIR = os.path.join(ROOT, "pilot", "multibench")
if MULTIBENCH_DIR not in sys.path:
    sys.path.insert(0, MULTIBENCH_DIR)

import tatqa_strategy_structure_audit as audit  # noqa: E402


class TatqaStrategyStructureAuditTest(unittest.TestCase):
    def test_derivation_normalization_removes_numbers_currency_and_percent(self):
        text = "($2,843 - $2,435)/$2,435"
        normalized = audit.normalized_derivation(text)
        self.assertEqual(normalized, "( O1 - O2 ) / O3")
        for forbidden in ["2,843", "2,435", "$"]:
            self.assertNotIn(forbidden, normalized)

    def test_operator_sequence_skips_unary_minus(self):
        tokens = audit.tokenize_derivation("-(39,185 + 37,035) / 2")
        self.assertEqual(audit.operator_sequence_from_tokens(tokens), ["add", "divide"])

    def test_percent_change_family(self):
        rec = {
            "sample_id": "tatqa:train:test",
            "source_id": "source",
            "answer_type": "arithmetic",
            "answer_from": "table",
            "scale": "percent",
            "derivation": "(16,284 - 6,509) / 6,509",
        }
        abstraction = audit.abstract_record(rec)
        self.assertEqual(abstraction["family"], "arithmetic:percent_change")
        self.assertEqual(abstraction["operator_sequence"], ["subtract", "divide"])
        self.assertEqual(abstraction["abstraction_reliability"], "high")

    def test_non_arithmetic_schema_is_not_arithmetic(self):
        rec = {
            "sample_id": "tatqa:train:test",
            "source_id": "source",
            "answer_type": "multi-span",
            "answer_from": "text",
            "scale": "",
            "question": "Which years had revenue growth?",
            "reasoning_annotation": {"req_comparison": False},
        }
        abstraction = audit.abstract_record(rec)
        self.assertEqual(abstraction["strategy_type"], "multi_span_lookup")
        self.assertIn("multi_span_lookup:text", abstraction["family"])


if __name__ == "__main__":
    unittest.main()
