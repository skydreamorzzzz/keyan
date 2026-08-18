"""QC Strategy(E) abstractions for leakage, structural preservation, hallucination, degeneracy.

Checks:
1. Leakage: company names, years, specific values, answers
2. Structural preservation: operation family, sequence, roles
3. Hallucination: operations not in source
4. Degeneracy: empty/generic templates
"""
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

def check_leakage(strategy: dict, case: dict) -> dict:
    """Check if Strategy leaks instance-specific details from Case."""
    issues = []

    # Get strategy text (combine all text fields)
    strategy_text = json.dumps(strategy).lower()

    # Check company name leakage
    company = case.get("company", "").lower()
    if company and len(company) > 3 and company in strategy_text:
        issues.append(f"company_name: {company}")

    # Check year leakage
    year_pattern = r'\b(19|20)\d{2}\b'
    years_in_strategy = set(re.findall(year_pattern, strategy_text))
    if years_in_strategy:
        issues.append(f"years: {years_in_strategy}")

    # Check specific value leakage (numbers from case answer)
    answer = str(case.get("answer", ""))
    # Extract numbers from answer
    answer_numbers = re.findall(r'\d+\.?\d*', answer)
    for num in answer_numbers:
        if len(num) > 2 and num in strategy_text:
            issues.append(f"answer_value: {num}")
            break

    # Check for specific company-related entities
    report_text = case.get("report_context", "").lower()
    # Extract potential entity names (capitalized phrases in original)
    entities = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', case.get("report_context", ""))
    leaked_entities = []
    for entity in entities[:20]:  # Check first 20 entities
        if len(entity) > 5 and entity.lower() in strategy_text:
            leaked_entities.append(entity)
    if leaked_entities:
        issues.append(f"entities: {leaked_entities[:3]}")

    return {
        "passed": len(issues) == 0,
        "issues": issues
    }

def check_structural_preservation(strategy: dict, case: dict) -> dict:
    """Check if Strategy preserves operation structure from Case."""
    issues = []

    case_program = case.get("program", [])
    strategy_text = json.dumps(strategy).lower()

    # Extract operations from case program
    case_ops = []
    for step in case_program:
        if isinstance(step, str):
            # Parse operation from string like "divide(#0, #1)"
            op_match = re.match(r'(\w+)\(', step)
            if op_match:
                case_ops.append(op_match.group(1))

    # Check if strategy mentions key operations
    key_ops = ['add', 'subtract', 'multiply', 'divide', 'table_sum', 'table_average', 'table_max', 'table_min']
    mentioned_ops = [op for op in key_ops if op in strategy_text or op.replace('_', ' ') in strategy_text]

    # If case has operations but strategy mentions none, flag it
    if case_ops and not mentioned_ops:
        issues.append("no_operations_mentioned")

    # Check if operation family is preserved
    case_op_set = set(case_ops)
    mentioned_op_set = set(mentioned_ops)

    # If case has specific ops but strategy doesn't mention any of them, flag
    if case_op_set and not (case_op_set & mentioned_op_set):
        # Allow for synonyms: divide→ratio, subtract→difference, etc.
        if 'divide' in case_op_set and ('ratio' in strategy_text or 'percentage' in strategy_text):
            pass  # OK
        elif 'subtract' in case_op_set and ('difference' in strategy_text or 'change' in strategy_text):
            pass  # OK
        else:
            issues.append(f"operation_mismatch: case={list(case_op_set)[:3]}, strategy={list(mentioned_op_set)[:3]}")

    return {
        "passed": len(issues) == 0,
        "issues": issues
    }

def check_hallucination(strategy: dict, case: dict) -> dict:
    """Check if Strategy adds operations/requirements not in source."""
    issues = []

    # This is hard to check deterministically without semantic understanding
    # For now, check if strategy is much longer than case complexity
    case_program = case.get("program", [])
    strategy_text = json.dumps(strategy)

    # If case is simple (1-2 ops) but strategy is very long, might be hallucinating
    if len(case_program) <= 2 and len(strategy_text) > 2000:
        issues.append("suspiciously_long_for_simple_case")

    return {
        "passed": len(issues) == 0,
        "issues": issues
    }

def check_degeneracy(strategy: dict) -> dict:
    """Check if Strategy is too generic/empty."""
    issues = []

    strategy_text = json.dumps(strategy).lower()

    # Check for generic phrases that provide no reusable reasoning
    generic_phrases = [
        "find relevant values",
        "calculate the answer",
        "look at the table",
        "use the information",
        "perform the calculation"
    ]

    generic_count = sum(1 for phrase in generic_phrases if phrase in strategy_text)

    # If strategy is very short, flag it
    if len(strategy_text) < 200:
        issues.append("too_short")

    # If strategy is mostly generic phrases, flag it
    if generic_count >= 3:
        issues.append("too_generic")

    # Check if strategy has actual procedural content
    # Look for operand roles or specific reasoning steps
    has_roles = 'operand' in strategy_text or 'role' in strategy_text or 'value' in strategy_text
    has_procedure = 'step' in strategy_text or 'then' in strategy_text or 'calculate' in strategy_text

    if not (has_roles or has_procedure):
        issues.append("no_procedural_content")

    return {
        "passed": len(issues) == 0,
        "issues": issues
    }

def main():
    print("=" * 80)
    print("STAGE 36: QC Strategy(E) Abstractions")
    print("=" * 80)
    print()

    # Load strategies
    strategies_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/strategies_raw.json")
    with open(strategies_file) as f:
        strategies = json.load(f)

    print(f"Loaded {len(strategies)} strategies")
    print()

    # Load cases for cross-reference
    cases_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/paired_sources.json")
    with open(cases_file) as f:
        cases_data = json.load(f)
        # paired_sources.json is a list, not dict with "cases" key
        cases = {c["source_experience_id"]: c for c in cases_data}

    print(f"Loaded {len(cases)} cases for cross-reference")
    print()

    # Run QC checks
    qc_results = []

    print("Running QC checks...")
    print()

    for strategy in strategies:
        source_id = strategy["source_experience_id"]
        case = cases.get(source_id)

        if not case:
            print(f"WARNING: No case found for strategy {source_id}")
            continue

        leakage = check_leakage(strategy, case)
        structural = check_structural_preservation(strategy, case)
        hallucination = check_hallucination(strategy, case)
        degeneracy = check_degeneracy(strategy)

        qc_result = {
            "source_experience_id": source_id,
            "leakage": leakage,
            "structural_preservation": structural,
            "hallucination": hallucination,
            "degeneracy": degeneracy,
            "overall_passed": all([
                leakage["passed"],
                structural["passed"],
                hallucination["passed"],
                degeneracy["passed"]
            ])
        }

        qc_results.append(qc_result)

    # Summary statistics
    print("=" * 80)
    print("QC SUMMARY")
    print("=" * 80)
    print()

    total = len(qc_results)
    passed = sum(1 for r in qc_results if r["overall_passed"])

    print(f"Total strategies: {total}")
    print(f"Passed all checks: {passed} ({passed/total*100:.1f}%)")
    print(f"Failed at least one check: {total - passed} ({(total-passed)/total*100:.1f}%)")
    print()

    # Breakdown by check type
    leakage_failures = sum(1 for r in qc_results if not r["leakage"]["passed"])
    structural_failures = sum(1 for r in qc_results if not r["structural_preservation"]["passed"])
    hallucination_failures = sum(1 for r in qc_results if not r["hallucination"]["passed"])
    degeneracy_failures = sum(1 for r in qc_results if not r["degeneracy"]["passed"])

    print("Failure breakdown:")
    print(f"  Leakage: {leakage_failures} ({leakage_failures/total*100:.1f}%)")
    print(f"  Structural preservation: {structural_failures} ({structural_failures/total*100:.1f}%)")
    print(f"  Hallucination: {hallucination_failures} ({hallucination_failures/total*100:.1f}%)")
    print(f"  Degeneracy: {degeneracy_failures} ({degeneracy_failures/total*100:.1f}%)")
    print()

    # Show examples of failures
    print("=" * 80)
    print("FAILURE EXAMPLES")
    print("=" * 80)
    print()

    # Leakage examples
    leakage_fails = [r for r in qc_results if not r["leakage"]["passed"]][:3]
    if leakage_fails:
        print("Leakage failures:")
        for r in leakage_fails:
            print(f"  {r['source_experience_id'][:16]}... Issues: {r['leakage']['issues']}")
        print()

    # Structural failures
    structural_fails = [r for r in qc_results if not r["structural_preservation"]["passed"]][:3]
    if structural_fails:
        print("Structural preservation failures:")
        for r in structural_fails:
            print(f"  {r['source_experience_id'][:16]}... Issues: {r['structural_preservation']['issues']}")
        print()

    # Degeneracy examples
    degeneracy_fails = [r for r in qc_results if not r["degeneracy"]["passed"]][:3]
    if degeneracy_fails:
        print("Degeneracy failures:")
        for r in degeneracy_fails:
            print(f"  {r['source_experience_id'][:16]}... Issues: {r['degeneracy']['issues']}")
        print()

    # Save QC results
    output_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/qc_results.json")
    with open(output_file, 'w') as f:
        json.dump(qc_results, f, indent=2)

    print(f"Saved QC results to {output_file}")
    print()

    # Decision gate
    print("=" * 80)
    print("DECISION GATE")
    print("=" * 80)
    print()

    if passed / total >= 0.80:
        print("✓ QC PASSED: ≥80% strategies passed all checks")
        print("  Proceed to shared-source retrieval protocol")
    elif passed / total >= 0.60:
        print("⚠ QC MARGINAL: 60-80% pass rate")
        print("  Consider filtering failed strategies or improving abstraction prompt")
    else:
        print("✗ QC FAILED: <60% pass rate")
        print("  Abstraction operator is unstable. Do NOT proceed to downstream experiment.")
        print("  Recommendation: Revise abstraction prompt or use different approach")
    print()

if __name__ == "__main__":
    main()
