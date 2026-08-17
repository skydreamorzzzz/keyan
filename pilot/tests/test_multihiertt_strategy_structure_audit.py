import unittest

from pilot.multibench.multihiertt_strategy_structure_audit import (
    abstract_record,
    operator_sequence,
    program_family,
    span_family,
    table_usage,
)


def base_row(program: str = "") -> dict:
    return {
        "uid": "u1",
        "question": "Which year is revenue the greatest?",
        "answer": "2019",
        "program": program,
        "paragraphs": ["## Table 1 ##"],
        "tables": ['<table><tr><th rowspan="2">Metric</th><th>2019</th></tr></table>'],
        "table_description": '{"0-0-1": "Revenue in 2019", "1-0-1": "Revenue in 2020"}',
        "text_evidence": [0],
        "table_evidence": ["0-0-1", "1-0-1"],
    }


class MultiHierttStrategyStructureAuditTest(unittest.TestCase):
    def test_program_operator_sequence_and_family(self) -> None:
        row = base_row("subtract(10,8), divide(#0,8)")

        self.assertEqual(operator_sequence(row["program"]), ["subtract", "divide"])
        self.assertEqual(program_family(row), "program:difference_then_ratio")

    def test_ratio_program_family_uses_question_intent(self) -> None:
        row = base_row("divide(10,8)")
        row["question"] = "What is the ratio of revenue to cost?"

        self.assertEqual(program_family(row), "program:ratio")

    def test_span_family_keeps_span_separate(self) -> None:
        row = base_row("")
        row["question"] = "Does 2019 revenue greater than 2018 revenue?"

        self.assertEqual(span_family(row), "span:comparison_yesno")

    def test_table_usage_detects_multi_table_and_hierarchy(self) -> None:
        usage = table_usage(base_row(""))

        self.assertTrue(usage["multi_table_evidence"])
        self.assertTrue(usage["has_hierarchy_markers"])
        self.assertEqual(usage["evidence_table_count"], 2)

    def test_abstract_record_schema_key_contains_safe_structure(self) -> None:
        row = base_row("add(10,8)")
        abstraction = abstract_record(row, 0)

        self.assertEqual(abstraction["answer_type"], "program")
        self.assertIn("program:aggregation_sum", abstraction["schema_key"])
        self.assertIn("ev=text+table", abstraction["schema_key"])
        self.assertEqual(abstraction["operand_count"], 2)


if __name__ == "__main__":
    unittest.main()
