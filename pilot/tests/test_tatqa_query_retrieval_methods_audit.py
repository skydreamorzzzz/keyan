import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MULTIBENCH_DIR = os.path.join(ROOT, "pilot", "multibench")
if MULTIBENCH_DIR not in sys.path:
    sys.path.insert(0, MULTIBENCH_DIR)

import tatqa_query_retrieval_methods_audit as audit  # noqa: E402


class TatqaQueryRetrievalMethodsAuditTest(unittest.TestCase):
    def test_prompt_mentions_forbidden_gold_fields_only_as_forbidden(self):
        prompt = audit.prompt_for_question("What was the change in revenue from 2018 to 2019?")
        self.assertIn("question", prompt)
        self.assertIn("Do not use or guess gold answer_type", prompt)
        self.assertNotIn("derivation:", prompt)
        self.assertNotIn("scale:", prompt)

    def test_parse_response_sanitizes_numbers(self):
        text = '{"query_rewrite":"percent change from 2018 to 2019 using 123", "hyde_strategy":"compute ($2,000 - $1,000) / $1,000"}'
        parsed = audit.parse_response(text)
        self.assertNotIn("2018", parsed["query_rewrite"])
        self.assertNotIn("123", parsed["query_rewrite"])
        self.assertNotIn("$2,000", parsed["hyde_strategy"])

    def test_choose_recommendation_prefers_schema_then_type(self):
        results = {
            "question_only": {"eligible_only": {"schema_top3": 0.2}, "overall": {"type_top3": 0.8}},
            "query_rewrite": {"eligible_only": {"schema_top3": 0.3}, "overall": {"type_top3": 0.5}},
            "hyde": {"eligible_only": {"schema_top3": 0.3}, "overall": {"type_top3": 0.7}},
        }
        self.assertEqual(audit.choose_recommendation(results), "hyde")


if __name__ == "__main__":
    unittest.main()
