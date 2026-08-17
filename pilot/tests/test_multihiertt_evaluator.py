import unittest

from pilot.multibench.multihiertt_evaluator import evaluate_one
from pilot.multibench.official_multihiertt.utils.program_generation_utils import (
    eval_program,
    program_tokenization,
)
from pilot.multibench.official_multihiertt.utils.span_selection_utils import get_span_selection_metrics
from pilot.multibench.official_multihiertt.utils.utils import str_to_num


class MultiHierttEvaluatorTest(unittest.TestCase):
    def test_program_prediction_executes_with_official_semantics(self) -> None:
        gold = {"uid": "p1", "answer": "5", "program": "add(2,3)"}
        result = evaluate_one(gold, {"predicted_program": "add(2,3)"})

        self.assertEqual(result["eval_mode"], "program_vs_program")
        self.assertEqual(result["em"], 1.0)
        self.assertEqual(result["f1"], 1.0)

    def test_answer_only_numeric_prediction_for_program_gold(self) -> None:
        gold = {"uid": "p2", "answer": "0.5", "program": "divide(1,2)"}
        result = evaluate_one(gold, {"predicted_ans": "0.5"})

        self.assertEqual(result["eval_mode"], "answer_vs_gold_program_execution")
        self.assertEqual(result["em"], 1.0)
        self.assertEqual(result["f1"], 1.0)

    def test_official_numeric_formatting_for_currency_comma_percent(self) -> None:
        self.assertEqual(str_to_num("$1,234.5"), 1234.5)
        self.assertEqual(str_to_num("12.5%"), 12.5)
        self.assertEqual(str_to_num("const_m1"), -1.0)

    def test_negative_number_compatibility_risk_is_official_behavior(self) -> None:
        # Official MultiHiertt str_to_num strips the hyphen. The wrapper records
        # this as a compatibility risk rather than changing evaluator semantics.
        self.assertEqual(str_to_num("-46.4"), 46.4)

    def test_program_can_execute_negative_constant(self) -> None:
        invalid, value = eval_program(program_tokenization("multiply(const_m1,5)"))

        self.assertEqual(invalid, 0)
        self.assertEqual(value, -5.0)

    def test_span_and_multi_span_metrics(self) -> None:
        self.assertEqual(get_span_selection_metrics("Net income", "net income"), (1.0, 1.0))
        self.assertEqual(get_span_selection_metrics(["cash flow", "revenue"], ["revenue", "cash flow"]), (1.0, 1.0))


if __name__ == "__main__":
    unittest.main()
