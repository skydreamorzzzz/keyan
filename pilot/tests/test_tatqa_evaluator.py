import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pilot", "multibench"))

from tatqa_evaluator import evaluate_contexts, parse_prediction_entry  # noqa: E402


def context_with(*qas):
    return [{"table": {"uid": "t", "table": []}, "paragraphs": [], "questions": list(qas)}]


class TatqaEvaluatorTest(unittest.TestCase):
    def test_gold_numeric_zero_is_not_treated_as_missing(self):
        gold = context_with({
            "uid": "q0",
            "answer": 0,
            "scale": "percent",
            "answer_type": "arithmetic",
            "answer_from": "table",
        })
        result = evaluate_contexts(gold, {"q0": [0, "percent"]})
        self.assertEqual(result["exact_match"], 1.0)
        self.assertEqual(result["f1"], 1.0)
        self.assertEqual(result["scale_score"], 1.0)

    def test_numeric_format_commas_match(self):
        gold = context_with({
            "uid": "q1",
            "answer": 1000,
            "scale": "",
            "answer_type": "arithmetic",
            "answer_from": "table",
        })
        result = evaluate_contexts(gold, {"q1": ["1,000", ""]})
        self.assertEqual(result["exact_match"], 1.0)

    def test_percent_decimal_without_scale_matches_official_special_case(self):
        gold = context_with({
            "uid": "q2",
            "answer": 4.6,
            "scale": "percent",
            "answer_type": "arithmetic",
            "answer_from": "table",
        })
        result = evaluate_contexts(gold, {"q2": ["0.046", ""]})
        self.assertEqual(result["exact_match"], 1.0)
        self.assertEqual(result["scale_score"], 0.0)

    def test_scale_mismatch_blocks_em_even_if_number_text_matches(self):
        gold = context_with({
            "uid": "q3",
            "answer": 4.6,
            "scale": "percent",
            "answer_type": "arithmetic",
            "answer_from": "table",
        })
        result = evaluate_contexts(gold, {"q3": ["4.6", ""]})
        self.assertEqual(result["exact_match"], 0.0)
        self.assertEqual(result["scale_score"], 0.0)

    def test_multi_span_order_invariant(self):
        gold = context_with({
            "uid": "q4",
            "answer": ["2018", "2019"],
            "scale": "",
            "answer_type": "multi-span",
            "answer_from": "table",
        })
        result = evaluate_contexts(gold, {"q4": [["2019", "2018"], ""]})
        self.assertEqual(result["exact_match"], 1.0)
        self.assertEqual(result["f1"], 1.0)

    def test_prediction_dict_format(self):
        answer, scale = parse_prediction_entry({"answer": 42, "scale": "million"})
        self.assertEqual(answer, "42")
        self.assertEqual(scale, "million")


if __name__ == "__main__":
    unittest.main()
