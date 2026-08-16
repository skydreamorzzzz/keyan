import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MULTIBENCH_DIR = os.path.join(ROOT, "pilot", "multibench")
if MULTIBENCH_DIR not in sys.path:
    sys.path.insert(0, MULTIBENCH_DIR)

import tatqa_strategy_memory_pilot as pilot  # noqa: E402


class TatqaStrategyMemoryPilotTest(unittest.TestCase):
    def test_deterministic_arithmetic_percent_change(self):
        group = {
            "family": "arithmetic:percent_change",
            "answer_from": "table",
            "scale": "percent",
        }
        semantic = pilot.deterministic_arithmetic_text(group)
        text = " ".join([semantic["description"], semantic["answer_form"], *semantic["risk_notes"]])
        self.assertIn("relative change", text)
        self.assertIn("percent", text)
        self.assertTrue(semantic["operand_roles"])

    def test_leak_hits_detects_year_and_number(self):
        hits = pilot.leak_hits("Use 2019 revenue and $2,500 as the answer.")
        types = {h["type"] for h in hits}
        self.assertIn("four_digit_year", types)
        self.assertIn("currency_or_large_number", types)

    def test_strategy_has_required_keys_after_build(self):
        group = {
            "schema_key": "arithmetic|arithmetic:difference|from=table|scale=million",
            "strategy_type": "arithmetic",
            "family": "arithmetic:difference",
            "answer_from": "table",
            "scale": "million",
            "support_count": 2,
            "items": [
                {
                    "record": {"question": "What was the change?", "sample_id": "tatqa:train:1"},
                    "abstraction": {"sample_id": "tatqa:train:1", "answer_from": "table", "scale": "million"},
                }
            ],
        }
        semantic = pilot.deterministic_arithmetic_text(group)
        strategy = pilot.build_strategy(group, semantic, {"method": "test"})
        self.assertFalse(pilot.REQUIRED_STRATEGY_KEYS - set(strategy))
        self.assertIn("Evidence source: table", strategy["retrieval_text"])


if __name__ == "__main__":
    unittest.main()
