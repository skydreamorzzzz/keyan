import unittest

from pilot.multibench.multihiertt_strategy_memory_pilot import (
    build_groups,
    group_examples,
    leak_hits,
    parse_llm_json,
    strategy_type,
)
from pilot.multibench.multihiertt_strategy_structure_audit import abstract_record


def row(uid: str, question: str, program: str, answer: str = "999") -> dict:
    return {
        "uid": uid,
        "question": question,
        "answer": answer,
        "program": program,
        "paragraphs": ["placeholder"],
        "tables": ['<table><tr><th rowspan="2">Metric</th></tr></table>'],
        "table_description": "{}",
        "text_evidence": [0],
        "table_evidence": ["0-0-1"],
    }


class MultiHierttStrategyMemoryPilotTest(unittest.TestCase):
    def test_group_examples_do_not_emit_numeric_counts(self) -> None:
        item = {"abstraction": abstract_record(row("u1", "What is the ratio?", "divide(10,2)"), 0)}
        examples = group_examples([item])

        self.assertEqual(examples[0]["step_count_bucket"], "one")
        self.assertEqual(examples[0]["operand_count_bucket"], "two")
        self.assertNotIn("step_count", examples[0])

    def test_strategy_type_keeps_span_and_program_separate(self) -> None:
        program_abs = abstract_record(row("u1", "What is the ratio?", "divide(10,2)"), 0)
        span_abs = abstract_record(row("u2", "Does revenue greater than cost?", ""), 1)

        self.assertEqual(strategy_type(program_abs), "program")
        self.assertEqual(strategy_type(span_abs), "span_comparison_yesno")

    def test_parse_llm_json_sanitizes_concrete_values(self) -> None:
        parsed = parse_llm_json(
            '{"description":"Use for 2019 values of $1,234.5.",'
            '"reasoning_guidance":["Compare 2020 and 2019."],'
            '"evidence_guidance":["Find table 3."],'
            '"operand_roles":["new value"],'
            '"answer_form":"numeric",'
            '"scale_notes":["percent"],'
            '"multi_table_notes":["use both tables"],'
            '"risk_notes":["avoid 12.5"]}'
        )

        text = str(parsed)
        self.assertNotIn("2019", text)
        self.assertNotIn("$1,234.5", text)
        self.assertFalse(leak_hits(text))

    def test_build_groups_uses_frozen_top_lists(self) -> None:
        rows = [
            row("u1", "What is the ratio?", "divide(10,2)"),
            row("u2", "Which year is revenue greatest?", ""),
        ]
        audit = {
            "top_coarse_families": {"program:ratio": 1, "span:superlative_lookup": 1},
            "top_schema_families": {
                abstract_record(rows[0], 0)["schema_key"]: 1,
                abstract_record(rows[1], 1)["schema_key"]: 1,
            },
        }

        groups = build_groups(rows, audit)

        self.assertEqual(len(groups), 4)
        self.assertEqual({g["level"] for g in groups}, {"coarse", "schema"})


if __name__ == "__main__":
    unittest.main()
