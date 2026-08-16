import importlib.util
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PILOT = os.path.join(ROOT, "pilot")
if PILOT not in sys.path:
    sys.path.insert(0, PILOT)

from executor import exec_program_re, match_result, match_result_legacy


def load_official_eval():
    path = os.path.join(ROOT, "analysis", "official_code", "evaluate.py")
    spec = importlib.util.spec_from_file_location("official_finqa_evaluate_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class OfficialExecutorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.official = load_official_eval()

    def check_split_prefix(self, split, n):
        with open(os.path.join(ROOT, "data", "finqa", f"{split}.json")) as f:
            data = json.load(f)[:n]
        for ex in data:
            program = ex["qa"]["program"]
            table = ex["table"]
            gold = ex["qa"]["exe_ans"]
            official_invalid, official_res = self.official.eval_program(self.official.program_tokenization(program), table)
            ok, local_res = exec_program_re(program, table)
            local_res_norm = round(float(local_res), 5) if isinstance(local_res, (int, float)) else local_res
            self.assertEqual(official_invalid == 0, ok, ex.get("id"))
            self.assertEqual(official_res, local_res_norm, ex.get("id"))
            self.assertEqual(official_invalid == 0 and official_res == gold, ok and match_result(local_res, gold), ex.get("id"))

    def test_dev_gold_programs_match_official_prefix(self):
        self.check_split_prefix("dev", 492)

    def test_train_gold_programs_match_official_prefix(self):
        self.check_split_prefix("train", 1000)

    def test_strict_differs_from_legacy_tolerance(self):
        self.assertFalse(match_result(1.000006, 1.0))
        self.assertTrue(match_result_legacy(1.000006, 1.0))


if __name__ == "__main__":
    unittest.main()
