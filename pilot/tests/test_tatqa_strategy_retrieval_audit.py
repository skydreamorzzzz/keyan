import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MULTIBENCH_DIR = os.path.join(ROOT, "pilot", "multibench")
if MULTIBENCH_DIR not in sys.path:
    sys.path.insert(0, MULTIBENCH_DIR)

import tatqa_strategy_retrieval_audit as audit  # noqa: E402


class TatqaStrategyRetrievalAuditTest(unittest.TestCase):
    def test_schema_only_text_excludes_semantic_fields(self):
        strategy = {
            "strategy_type": "span_lookup",
            "family": "span_lookup:text:scale=none",
            "schema_key": "span_lookup|span_lookup:text:scale=none|from=text|scale=none",
            "answer_from": "text",
            "scale": "none",
            "description": "semantic description should not appear",
            "evidence_guidance": ["semantic evidence should not appear"],
            "retrieval_text": "semantic rich text",
        }
        text = audit.schema_only_text(strategy)
        self.assertIn("span_lookup:text:scale=none", text)
        self.assertNotIn("semantic description", text)
        self.assertNotIn("semantic evidence", text)

    def test_compatibility_exact_and_partial(self):
        absr = {
            "schema_key": "schema-a",
            "strategy_type": "arithmetic",
            "family": "arithmetic:ratio",
            "answer_from": "table",
            "scale": "percent",
        }
        hits = [
            {"schema_key": "schema-b", "strategy_type": "arithmetic", "family": "arithmetic:ratio", "answer_from": "text", "scale": "none"},
            {"schema_key": "schema-a", "strategy_type": "arithmetic", "family": "arithmetic:ratio", "answer_from": "table", "scale": "percent"},
        ]
        c = audit.compatibility(absr, hits)
        self.assertFalse(c["schema_top1"])
        self.assertTrue(c["schema_topk"])
        self.assertTrue(c["type_top1"])
        self.assertTrue(c["answer_from_topk"])
        self.assertTrue(c["scale_topk"])


if __name__ == "__main__":
    unittest.main()
