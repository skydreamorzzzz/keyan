import os
import sys
import unittest
from unittest import mock

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MULTIBENCH_DIR = os.path.join(ROOT, "pilot", "multibench")
if MULTIBENCH_DIR not in sys.path:
    sys.path.insert(0, MULTIBENCH_DIR)

import tatqa_case_memory as tcm  # noqa: E402


class DummyModel:
    def encode(self, texts, **kwargs):
        vectors = []
        for text in texts:
            if "query" in text:
                vectors.append([1.0, 0.0])
            elif "same-source" in text:
                vectors.append([0.95, 0.05])
            else:
                vectors.append([0.8, 0.2])
        return np.array(vectors, dtype=float)


class TatqaCaseMemoryTest(unittest.TestCase):
    def test_target_retrieval_text_uses_visible_fields_only(self):
        rec = {
            "question": "What was query revenue?",
            "paragraphs": [{"order": 1, "text": "Revenue was reported in the annual filing."}],
            "table": [["metric", "2020"], ["revenue", "10"]],
            "answer": "SECRET_ANSWER",
            "answer_type": "arithmetic",
            "answer_from": "table",
            "scale": "million",
            "operator": "divide",
            "derivation": "SECRET_DERIVATION",
            "reasoning_annotation": {"rel_paragraphs": ["1"]},
        }
        text = tcm.make_retrieval_text(rec, memory_side=False)
        self.assertIn("What was query revenue?", text)
        self.assertIn("Revenue was reported", text)
        self.assertIn("revenue | 10", text)
        for forbidden in ["SECRET_ANSWER", "arithmetic", "million", "divide", "SECRET_DERIVATION"]:
            self.assertNotIn(forbidden, text)

    def test_case_retrieval_text_uses_relevant_paragraphs_without_labels(self):
        rec = {
            "question": "What was revenue?",
            "relevant_paragraphs": [{"order": 2, "text": "Relevant paragraph."}],
            "paragraphs": [{"order": 1, "text": "Irrelevant paragraph."}],
            "table": [["metric", "2020"], ["revenue", "10"]],
            "answer": "SECRET_ANSWER",
            "scale": "percent",
            "operator": "subtract",
            "derivation": "SECRET_DERIVATION",
        }
        text = tcm.make_retrieval_text(rec, memory_side=True)
        self.assertIn("Relevant paragraph", text)
        self.assertNotIn("Irrelevant paragraph", text)
        for forbidden in ["SECRET_ANSWER", "percent", "subtract", "SECRET_DERIVATION"]:
            self.assertNotIn(forbidden, text)

    def test_retrieve_cases_excludes_source_id(self):
        emb = np.array([[0.99, 0.01], [0.8, 0.2]], dtype=float)
        order = [
            {"case_id": "same-source", "source_id": "source-a"},
            {"case_id": "other-source", "source_id": "source-b"},
        ]
        with mock.patch.object(tcm, "load_case_index", return_value=(emb, order)):
            with mock.patch.object(tcm, "get_model", return_value=DummyModel()):
                hits = tcm.retrieve_cases("query", k=1, exclude_source_id="source-a")
        self.assertEqual(hits[0]["case_id"], "other-source")
        self.assertEqual(hits[0]["source_id"], "source-b")


if __name__ == "__main__":
    unittest.main()
