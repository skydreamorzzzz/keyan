import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MULTIBENCH_DIR = os.path.join(ROOT, "pilot", "multibench")
if MULTIBENCH_DIR not in sys.path:
    sys.path.insert(0, MULTIBENCH_DIR)

import tatqa_heldout_four_arm_diagnostic as heldout  # noqa: E402
from tatqa_ingest import parse_split  # noqa: E402
from tatqa_strategy_retrieval_audit import AUDIT_N, fixed_dev_sample  # noqa: E402


class TatqaHeldoutFourArmDiagnosticTest(unittest.TestCase):
    def test_heldout_sample_excludes_previous_strategy_audit_sample(self):
        dev = parse_split("dev")
        previous_ids = {rec["sample_id"] for rec in fixed_dev_sample(dev, AUDIT_N)}
        sample, info = heldout.select_heldout_sample()
        sample_ids = {rec["sample_id"] for rec in sample}
        self.assertEqual(len(sample), heldout.HELDOUT_N)
        self.assertEqual(len(sample_ids), heldout.HELDOUT_N)
        self.assertFalse(sample_ids & previous_ids)
        self.assertEqual(info["previous_exclusion_n"], AUDIT_N)


if __name__ == "__main__":
    unittest.main()
