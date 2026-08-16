import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MULTIBENCH_DIR = os.path.join(ROOT, "pilot", "multibench")
if MULTIBENCH_DIR not in sys.path:
    sys.path.insert(0, MULTIBENCH_DIR)

import tatqa_four_arm_dry_run as dry_run  # noqa: E402


class TatqaFourArmDryRunTest(unittest.TestCase):
    def test_parse_answer_normalizes_none_scale(self):
        parsed, err = dry_run.parse_answer('{"answer": "revenue", "scale": "none"}')
        self.assertIsNone(err)
        self.assertEqual(parsed, {"answer": "revenue", "scale": ""})

    def test_parse_answer_rejects_invalid_scale(self):
        parsed, err = dry_run.parse_answer('{"answer": 1, "scale": "dollars"}')
        self.assertEqual(parsed, {"answer": 1, "scale": "dollars"})
        self.assertEqual(err, "invalid_scale:dollars")


if __name__ == "__main__":
    unittest.main()
