import unittest
from pipeline.programs import ProgramError, parse_strict
from pipeline.evaluator import evaluate_strict

class StrictMetricTests(unittest.TestCase):
    def test_whitespace_and_marker_are_safe(self):
        result=evaluate_strict("  add(1, 2) EOF ",3,[])
        self.assertTrue(result["valid_program"]); self.assertTrue(result["execution_accuracy"])
    def test_comma_repair_is_not_permitted(self):
        result=evaluate_strict("add(1 2)",3,[])
        self.assertFalse(result["valid_program"])
    def test_forward_reference_is_rejected(self):
        with self.assertRaises(ProgramError): parse_strict("add(#0, 1)")

if __name__ == "__main__": unittest.main()
