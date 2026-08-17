import unittest

from pilot.multibench.multihiertt_case_memory import (
    answer_type,
    build_case,
    evidence_modality,
    make_case_retrieval_text,
    make_target_retrieval_text,
    operator_family,
    source_hash,
)


def sample_row(program: str = "divide(10,2)") -> dict:
    return {
        "uid": "u1",
        "paragraphs": ["Company revenue was disclosed.", "The ratio is discussed elsewhere."],
        "tables": ["<table><tr><td>Revenue</td><td>10</td></tr></table>"],
        "table_description": '{"0-0": "Revenue label", "0-1": "Revenue value 10"}',
        "question": "What is the ratio?",
        "answer": "5",
        "program": program,
        "text_evidence": [0],
        "table_evidence": ["0-1"],
    }


class MultiHierttCaseMemoryTest(unittest.TestCase):
    def test_source_hash_uses_document_not_question_or_answer(self) -> None:
        a = sample_row()
        b = sample_row()
        b["uid"] = "different"
        b["question"] = "Different question?"
        b["answer"] = "999"

        self.assertEqual(source_hash(a), source_hash(b))

    def test_answer_and_operator_families(self) -> None:
        self.assertEqual(answer_type(sample_row("")), "span")
        self.assertEqual(answer_type(sample_row("add(1,2)")), "program")
        self.assertEqual(operator_family(sample_row("subtract(4,2), divide(#0,2)")), "divide+subtract")
        self.assertEqual(evidence_modality(sample_row()), "text+table")

    def test_retrieval_text_excludes_answer_and_program(self) -> None:
        row = sample_row("divide(10,2)")
        case = build_case(row, "train", 0)

        target_text = make_target_retrieval_text(row)
        case_text = make_case_retrieval_text(case)

        self.assertNotIn("divide(10,2)", target_text)
        self.assertNotIn("divide(10,2)", case_text)
        self.assertNotIn("answer", target_text.lower())
        self.assertIn("Revenue value 10", case_text)


if __name__ == "__main__":
    unittest.main()
