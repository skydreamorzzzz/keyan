import unittest

from pilot.multibench.multihiertt_ingest import parse_program, parse_row


class MultiHierttIngestTest(unittest.TestCase):
    def test_empty_program_is_span_answer(self) -> None:
        parsed = parse_program("")

        self.assertEqual(parsed["answer_type"], "span")
        self.assertEqual(parsed["operator_sequence"], [])
        self.assertEqual(parsed["operands"], [])
        self.assertEqual(parsed["n_steps"], 0)
        self.assertTrue(parsed["parse_ok"])

    def test_program_operator_sequence_and_operands(self) -> None:
        parsed = parse_program("add(1, 2), divide(#0, const_2)")

        self.assertEqual(parsed["answer_type"], "program")
        self.assertEqual(parsed["operator_sequence"], ["add", "divide"])
        self.assertEqual(parsed["operands"], [["1", "2"], ["#0", "const_2"]])
        self.assertEqual(parsed["n_steps"], 2)
        self.assertTrue(parsed["parse_ok"])

    def test_parse_row_preserves_multitable_ir_and_evidence(self) -> None:
        row = {
            "uid": "doc_1_q_0",
            "paragraphs": ["Intro text", "## Table 1 ##", "Follow-up text"],
            "tables": ["<table><tr><td>A</td></tr></table>", "<table><tr><td>B</td></tr></table>"],
            "table_description": '{"0-0": "first cell", "1-0": "second table first cell"}',
            "question": "What is the ratio?",
            "answer": "2",
            "program": "divide(4, 2)",
            "text_evidence": [0, 2],
            "table_evidence": ["0-0", "missing-cell"],
        }

        rec = parse_row("train", row, 7)

        self.assertEqual(rec["dataset_id"], "multihiertt")
        self.assertEqual(rec["sample_id"], "multihiertt:train:doc_1_q_0")
        self.assertEqual(rec["question"], "What is the ratio?")
        self.assertEqual(len(rec["tables"]), 2)
        self.assertEqual(rec["tables"][0]["format"], "html")
        self.assertIn("paragraph_0: Intro text", rec["text_context"])
        self.assertEqual(rec["reasoning"]["program"], "divide(4, 2)")
        self.assertEqual(rec["reasoning"]["operator_sequence"], ["divide"])
        self.assertEqual(rec["reasoning"]["evidence"]["text"][0]["text"], "Intro text")
        self.assertTrue(rec["reasoning"]["evidence"]["table"][0]["valid"])
        self.assertFalse(rec["reasoning"]["evidence"]["table"][1]["valid"])
        self.assertEqual(rec["raw_metadata"]["table_count"], 2)
        self.assertTrue(rec["raw_metadata"]["table_description_parse_ok"])


if __name__ == "__main__":
    unittest.main()
