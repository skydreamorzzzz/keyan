import os
import sys
import tempfile
import unittest
import json

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pilot", "stage4b"))
sys.path.insert(0, os.path.join(ROOT, "pilot", "stage3"))

from run_development_nested import choices_hierarchical  # noqa: E402
from run_development_nested import se as inner_se  # noqa: E402
from stage4b_common import conservative_select, evaluate_realized_by_replicate  # noqa: E402
from stability_run import JsonlCache  # noqa: E402


class Stage4BProtocolTest(unittest.TestCase):
    def test_inner_se_uses_sample_standard_deviation(self):
        self.assertAlmostEqual(inner_se([0.0, 1.0]), 0.5)

    def test_realized_gain_is_policy_accuracy_minus_both_accuracy(self):
        records = [
            {
                "replicate_correctness": {
                    "rn1": {"none": 1, "case": 0, "strategy": 0, "both": 0},
                    "rn2": {"none": 1, "case": 0, "strategy": 0, "both": 0},
                    "rn3": {"none": 0, "case": 0, "strategy": 0, "both": 1},
                }
            },
            {
                "replicate_correctness": {
                    "rn1": {"none": 1, "case": 0, "strategy": 0, "both": 1},
                    "rn2": {"none": 0, "case": 0, "strategy": 0, "both": 1},
                    "rn3": {"none": 0, "case": 0, "strategy": 0, "both": 1},
                }
            },
        ]
        out = evaluate_realized_by_replicate(records, ["none", "none"])
        self.assertEqual(out["rn1"]["policy_accuracy"], 1.0)
        self.assertEqual(out["rn1"]["both_accuracy"], 0.5)
        self.assertEqual(out["rn1"]["gain_vs_both"], 0.5)
        for rep in ["rn1", "rn2", "rn3"]:
            self.assertAlmostEqual(
                out[rep]["gain_vs_both"],
                out[rep]["policy_accuracy"] - out[rep]["both_accuracy"],
            )

    def test_conservative_select_prefers_both_within_one_se(self):
        selected = conservative_select([
            {
                "architecture": "flat_delta",
                "feature_set": "existing_meta",
                "threshold": 0.0,
                "lambda": None,
                "mean_gain": 0.01,
                "se_gain": 0.02,
                "coverage": 0.2,
            },
            {
                "architecture": "always_both",
                "feature_set": "none",
                "threshold": None,
                "lambda": None,
                "mean_gain": 0.0,
                "se_gain": 0.0,
                "coverage": 0.0,
            },
        ])
        self.assertEqual(selected["architecture"], "always_both")

    def test_hierarchical_case_gate_abstains_instead_of_second_choice(self):
        pred = {
            "gate_prob": [0.55],
            "arm_prob": {
                "none": [0.30],
                "case": [0.60],
                "strategy": [0.10],
            },
        }
        self.assertEqual(choices_hierarchical(pred, [7], threshold=0.5), {7: "both"})

    def test_jsonl_cache_rejects_runtime_drift_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cache.jsonl")
            recs = [
                {
                    "key": "a",
                    "out": "x",
                    "runtime": {
                        "response_model": "deepseek-v4-flash",
                        "effective_model": "deepseek-v4-flash",
                        "system_fingerprint": "fp1",
                        "thinking_mode": False,
                        "temperature": 0,
                        "max_tokens": 600,
                    },
                },
                {
                    "key": "b",
                    "out": "y",
                    "runtime": {
                        "response_model": "deepseek-v4-flash",
                        "effective_model": "deepseek-v4-flash",
                        "system_fingerprint": "fp2",
                        "thinking_mode": False,
                        "temperature": 0,
                        "max_tokens": 600,
                    },
                },
            ]
            with open(path, "w") as f:
                for rec in recs:
                    f.write(json.dumps(rec) + "\n")
            with self.assertRaises(RuntimeError):
                JsonlCache(path)

    def test_jsonl_cache_validates_runtime_on_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cache.jsonl")
            runtime = {
                "response_model": "deepseek-v4-flash",
                "effective_model": "deepseek-v4-flash",
                "system_fingerprint": "fp1",
                "thinking_mode": False,
                "temperature": 0,
                "max_tokens": 600,
            }
            with open(path, "w") as f:
                f.write(json.dumps({"key": "a", "out": "x", "runtime": runtime}) + "\n")
            cache = JsonlCache(path)
            cache.cache["a"]["runtime"] = {**runtime, "system_fingerprint": "fp2"}
            with self.assertRaises(RuntimeError):
                cache.call("a", "prompt", "system")


if __name__ == "__main__":
    unittest.main()
