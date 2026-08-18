#!/usr/bin/env python3
"""
Regression tests for canonical evaluator

Test categories:
1. FinQA gold programs (should all execute correctly)
2. Case sensitivity (PROGRAM vs Program vs program)
3. Malformed programs (partial operations, unmatched parens)
4. Multiline programs
5. Operator-only programs
6. Nested vs linear formats
7. const_X and #N references
8. Table operations
"""

import json
import sys
sys.path.insert(0, '/home/tiantian/keyan/pilot/stage36_paired_abstraction')
from canonical_evaluator import (
    extract_program_case_insensitive,
    normalize_program,
    check_operator_only,
    parse_program_safe,
    execute_program_canonical,
    evaluate_response
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

    print("=" * 60)
    print("TEST: Case-insensitive PROGRAM extraction")
    print("=" * 60)

    passed = 0
    for response, expected in tests:
        result = extract_program_case_insensitive(response)
        status = "✓" if result == expected else "✗"
        print(f"{status} Input: {response[:40]}... -> {result}")
        if result == expected:
            passed += 1

    print(f"\nPassed: {passed}/{len(tests)}\n")
    return passed == len(tests)


def test_multiline_normalization():
    """Test multiline program normalization."""
    tests = [
        ("divide(1, 2)\nmultiply(#0, 100)", "divide(1, 2), multiply(#0, 100)"),
        ("divide(1, 2),\nmultiply(#0, 100)", "divide(1, 2), multiply(#0, 100)"),
        ("divide(1, 2)\n\nmultiply(#0, 100)", "divide(1, 2), multiply(#0, 100)"),
    ]

    print("=" * 60)
    print("TEST: Multiline normalization")
    print("=" * 60)

    passed = 0
    for raw, expected in tests:
        result = normalize_program(raw)
        status = "✓" if result == expected else "✗"
        print(f"{status} {repr(raw)} -> {repr(result)}")
        if result == expected:
            passed += 1

    print(f"\nPassed: {passed}/{len(tests)}\n")
    return passed == len(tests)


def test_operator_only_detection():
    """Test operator-only program detection."""
    tests = [
        ("subtract, divide, multiply", True),
        ("divide, multiply", True),
        ("table_max, divide", True),
        ("divide(1, 2)", False),
        ("divide(1, 2), multiply(#0, 100)", False),
        ("", False),
    ]

    print("=" * 60)
    print("TEST: Operator-only detection")
    print("=" * 60)

    passed = 0
    for program, expected in tests:
        result = check_operator_only(program)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{program}' -> {result}")
        if result == expected:
            passed += 1

    print(f"\nPassed: {passed}/{len(tests)}\n")
    return passed == len(tests)


def test_parse_linear_and_nested():
    """Test parsing of linear and nested formats."""
    tests = [
        # Linear format (top-level commas)
        ("divide(1, 2), multiply(#0, 100)", 2, True),
        ("subtract(100, 50), divide(#0, 50), multiply(#1, 100)", 3, True),

        # Nested format (single expression)
        ("divide(subtract(100, 50), 50)", 2, True),
        ("multiply(divide(1, 2), 100)", 2, True),

        # Edge cases
        ("divide(1, 2)", 1, True),
        ("", 0, False),
    ]

    print("=" * 60)
    print("TEST: Parse linear and nested formats")
    print("=" * 60)

    passed = 0
    for program, expected_steps, should_succeed in tests:
        steps, error = parse_program_safe(program)

        if should_succeed:
            success = (steps is not None and len(steps) == expected_steps)
            status = "✓" if success else "✗"
            print(f"{status} '{program}' -> {len(steps) if steps else 0} steps")
        else:
            success = (steps is None)
            status = "✓" if success else "✗"
            print(f"{status} '{program}' -> should fail, got: {steps}")

        if success:
            passed += 1

    print(f"\nPassed: {passed}/{len(tests)}\n")
    return passed == len(tests)


def test_const_and_references():
    """Test const_X and #N reference handling."""
    tests = [
        ("divide(1, 2), multiply(#0, const_100)", 2, True),
        ("subtract(10, const_1)", 1, True),
        ("multiply(5, const_m1)", 1, True),
        ("add(#0, #1)", 1, True),
    ]

    print("=" * 60)
    print("TEST: const_X and #N references")
    print("=" * 60)

    passed = 0
    for program, expected_steps, should_succeed in tests:
        steps, error = parse_program_safe(program)

        success = (steps is not None and len(steps) == expected_steps)
        status = "✓" if success else "✗"
        print(f"{status} '{program}' -> {len(steps) if steps else 0} steps")

        if success:
            passed += 1

    print(f"\nPassed: {passed}/{len(tests)}\n")
    return passed == len(tests)


def test_execution_with_mock_table():
    """Test execution with mock table."""
    mock_table = [
        ['revenue', 100, 200, 300],
        ['cost', 50, 100, 150],
    ]

    tests = [
        # Simple arithmetic
        ([('add', '10', '20')], True, 30.0),
        ([('divide', '100', '50')], True, 2.0),
        ([('multiply', '5', '10')], True, 50.0),

        # With references
        ([('divide', '100', '50'), ('multiply', '#0', '100')], True, 200.0),

        # With const
        ([('subtract', '10', 'const_1')], True, 9.0),
        ([('multiply', '5', 'const_100')], True, 500.0),

        # Table operations
        ([('table_max', 'revenue', 'none')], True, 300.0),
        ([('table_sum', 'cost', 'none')], True, 300.0),
    ]

    print("=" * 60)
    print("TEST: Execution with mock table")
    print("=" * 60)

    passed = 0
    for steps, should_succeed, expected_result in tests:
        success, result, error = execute_program_canonical(steps, mock_table)

        if should_succeed:
            matches = success and abs(result - expected_result) < 1e-4
            status = "✓" if matches else "✗"
            print(f"{status} {steps[0][0]} -> {result} (expected {expected_result})")
            if matches:
                passed += 1
        else:
            matches = not success
            status = "✓" if matches else "✗"
            print(f"{status} {steps[0][0]} -> should fail")
            if matches:
                passed += 1

    print(f"\nPassed: {passed}/{len(tests)}\n")
    return passed == len(tests)


def test_gold_programs_sample():
    """Test with sample gold programs from FinQA."""
    print("=" * 60)
    print("TEST: FinQA gold programs (sample)")
    print("=" * 60)

    # Load a few targets
    with open('/home/tiantian/keyan/pilot/stage36_paired_abstraction/expanded_sample_queries.json') as f:
        targets = json.load(f)

    sample_targets = targets[:10]

    passed = 0
    for target in sample_targets:
        gold_program = target['qa']['program']
        gold_answer = target['qa']['exe_ans']
        table = target.get('table', [])

        # Parse and execute
        steps, error = parse_program_safe(gold_program)

        if steps is None:
            print(f"✗ {target['id']}: Parse failed - {error}")
            continue

        success, result, exec_error = execute_program_canonical(steps, table)

        if not success:
            print(f"✗ {target['id']}: Execution failed - {exec_error}")
            continue

        # Check correctness
        correct = abs(float(result) - float(gold_answer)) < 1e-4
        status = "✓" if correct else "✗"
        print(f"{status} {target['id']}: {result:.5f} vs {gold_answer:.5f}")

        if correct:
            passed += 1

    print(f"\nPassed: {passed}/{len(sample_targets)}\n")
    return passed >= len(sample_targets) * 0.8  # Allow 80% pass rate


def run_all_tests():
    """Run all test suites."""
    print("\n" + "=" * 80)
    print("CANONICAL EVALUATOR REGRESSION TESTS")
    print("=" * 80 + "\n")

    tests = [
        ("Case-insensitive extraction", test_case_insensitive_extraction),
        ("Multiline normalization", test_multiline_normalization),
        ("Operator-only detection", test_operator_only_detection),
        ("Parse linear and nested", test_parse_linear_and_nested),
        ("const_X and #N references", test_const_and_references),
        ("Execution with mock table", test_execution_with_mock_table),
        ("FinQA gold programs", test_gold_programs_sample),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"ERROR in {name}: {e}")
            results.append((name, False))

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")

    total_passed = sum(1 for _, p in results if p)
    print(f"\nTotal: {total_passed}/{len(results)} test suites passed")
    print("=" * 80 + "\n")

    return total_passed == len(results)


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
