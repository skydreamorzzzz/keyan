#!/usr/bin/env python3
"""
Comprehensive Regression Tests for Canonical Evaluator V2

Requirements:
1. All 224 gold programs from expanded_sample_queries must parse and execute correctly
2. Malformed programs must fail as expected
3. No 80% threshold - must be 100% pass for expected-pass, 100% fail for expected-fail
"""

import json
import sys
sys.path.insert(0, '/home/tiantian/keyan/pilot/stage36_paired_abstraction')
from canonical_evaluator_v2 import (
    parse_program_v2_strict,
    execute_program_v2,
    check_correctness_v2,
    extract_program_case_insensitive,
    normalize_program_v2,
    check_operator_only
)


def test_case_insensitive_extraction():
    """Test PROGRAM marker case insensitivity."""
    tests = [
        ("PROGRAM: divide(1, 2)\nANSWER: 0.5", "divide(1, 2)"),
        ("Program: divide(1, 2)\nANSWER: 0.5", "divide(1, 2)"),
        ("program: divide(1, 2)\nANSWER: 0.5", "divide(1, 2)"),
        ("PrOgRaM: divide(1, 2)\nANSWER: 0.5", "divide(1, 2)"),
        ("No program here\nANSWER: 0.5", None),
    ]

    print("="*60)
    print("TEST: Case-insensitive PROGRAM extraction")
    print("="*60)

    passed = 0
    for response, expected in tests:
        result = extract_program_case_insensitive(response)
        status = "✓" if result == expected else "✗"
        if result == expected:
            passed += 1
        else:
            print(f"{status} FAILED: expected {expected}, got {result}")

    print(f"Passed: {passed}/{len(tests)}")
    return passed == len(tests)


def test_malformed_programs():
    """
    Test that malformed programs fail as expected.

    NO partial parsing allowed.
    """
    # These should ALL fail parsing
    malformed_cases = [
        ("divide(1, 2) garbage", "trailing content"),
        ("divide(1, 2), multiply(", "incomplete operation"),
        ("divide(1, 2), nonsense", "malformed operation"),
        ("divide(1, 2), multiply(#0, 100) trailing", "trailing content"),
        ("divide(1, 2 extra)", "invalid argument"),
        ("divide(1, 2))", "extra closing paren"),
        ("add(1, 2),", "dangling comma"),
        ("multiply(divide(1,2),100) garbage", "trailing content"),
        ("add()", "wrong arg count"),
        ("subtract(1)", "wrong arg count"),
        ("unknown_op(1, 2)", "unknown operation"),
        ("divide(1, 2", "unmatched paren"),
        ("divide 1, 2)", "missing opening paren"),
        ("divide(1, 2, 3)", "too many args"),
        ("", "empty"),
        ("   ", "whitespace only"),
    ]

    print("\n" + "="*60)
    print("TEST: Malformed programs (must all fail)")
    print("="*60)

    passed = 0
    for program, reason in malformed_cases:
        steps, error = parse_program_v2_strict(program)

        if steps is None:
            # Good - it failed as expected
            passed += 1
            print(f"✓ Correctly rejected ({reason}): '{program[:40]}'")
        else:
            # Bad - it should have failed
            print(f"✗ FAILED TO REJECT ({reason}): '{program[:40]}' -> {steps}")

    print(f"\nPassed: {passed}/{len(malformed_cases)}")
    return passed == len(malformed_cases)


def test_well_formed_programs():
    """Test that well-formed programs parse correctly."""
    well_formed_cases = [
        ("divide(1, 2)", 1),
        ("add(10, 20)", 1),
        ("subtract(100, 50), divide(#0, 50)", 2),
        ("divide(1, 2), multiply(#0, 100)", 2),
        ("subtract(1505, 2504), divide(#0, 2504), multiply(#1, const_100)", 3),
        ("multiply(divide(1, 2), 100)", 2),  # nested
        ("divide(subtract(100, 50), 50)", 2),  # nested
        ("table_max(revenue, none)", 1),
        ("subtract(10, const_1)", 1),
        ("multiply(5, const_m1)", 1),
    ]

    print("\n" + "="*60)
    print("TEST: Well-formed programs (must all parse)")
    print("="*60)

    passed = 0
    for program, expected_steps in well_formed_cases:
        steps, error = parse_program_v2_strict(program)

        if steps is not None and len(steps) == expected_steps:
            passed += 1
            print(f"✓ Parsed correctly: '{program[:40]}' -> {len(steps)} steps")
        else:
            print(f"✗ FAILED: '{program[:40]}' expected {expected_steps} steps, got {steps if steps else error}")

    print(f"\nPassed: {passed}/{len(well_formed_cases)}")
    return passed == len(well_formed_cases)


def test_gold_programs_complete():
    """
    Test ALL 224 gold programs from expanded_sample_queries.

    NO 80% threshold. Must be 224/224.
    """
    print("\n" + "="*60)
    print("TEST: All 224 FinQA gold programs")
    print("="*60)

    # Load targets
    with open('/home/tiantian/keyan/pilot/stage36_paired_abstraction/expanded_sample_queries.json') as f:
        targets = json.load(f)

    total = len(targets)
    parse_success = 0
    exec_success = 0
    match_success = 0

    failures = []

    for target in targets:
        target_id = target['id']
        gold_program = target['qa']['program']
        gold_answer = target['qa']['exe_ans']
        table = target.get('table', [])

        # Parse
        steps, parse_error = parse_program_v2_strict(gold_program)
        if steps is None:
            failures.append({
                'target_id': target_id,
                'stage': 'parse',
                'error': parse_error,
                'program': gold_program[:100]
            })
            continue

        parse_success += 1

        # Execute
        success, result, exec_error = execute_program_v2(steps, table)
        if not success:
            failures.append({
                'target_id': target_id,
                'stage': 'execution',
                'error': exec_error,
                'program': gold_program[:100]
            })
            continue

        exec_success += 1

        # Match
        correct, match_error = check_correctness_v2(result, gold_answer)
        if not correct:
            failures.append({
                'target_id': target_id,
                'stage': 'match',
                'error': match_error if match_error else f'got {result}, expected {gold_answer}',
                'program': gold_program[:100]
            })
            continue

        match_success += 1

    print(f"\nResults:")
    print(f"  Total:       {total}")
    print(f"  Parse OK:    {parse_success}")
    print(f"  Execute OK:  {exec_success}")
    print(f"  Match OK:    {match_success}")
    print()

    if match_success == total:
        print(f"✓ SUCCESS: {total}/{total} gold programs passed")
        return True
    else:
        print(f"✗ FAILED: {match_success}/{total} gold programs passed")
        print(f"\nFailed targets ({len(failures)}):")
        for f in failures[:20]:  # Show first 20
            print(f"  {f['target_id']}: {f['stage']} - {f['error']}")
            print(f"    Program: {f['program']}")

        if len(failures) > 20:
            print(f"  ... and {len(failures) - 20} more")

        return False


def run_all_tests():
    """Run all test suites."""
    print("\n" + "="*80)
    print("CANONICAL EVALUATOR V2 - COMPREHENSIVE REGRESSION TESTS")
    print("="*80 + "\n")

    tests = [
        ("Case-insensitive extraction", test_case_insensitive_extraction),
        ("Malformed programs (must fail)", test_malformed_programs),
        ("Well-formed programs (must pass)", test_well_formed_programs),
        ("All 224 FinQA gold programs", test_gold_programs_complete),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\nERROR in {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")

    total_passed = sum(1 for _, p in results if p)
    print(f"\nTotal: {total_passed}/{len(results)} test suites passed")

    if total_passed == len(results):
        print("\n✓✓✓ ALL TESTS PASSED ✓✓✓")
    else:
        print("\n✗✗✗ SOME TESTS FAILED ✗✗✗")

    print("="*80 + "\n")

    return total_passed == len(results)


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
