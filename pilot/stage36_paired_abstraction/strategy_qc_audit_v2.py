#!/usr/bin/env python3
"""
Strategy QC Audit V2

Comprehensive quality control for Format-Neutral strategy abstractions.

Checks:
1. Operation fidelity: Do operations match gold program?
2. Scale fidelity: Are there spurious ×100, /100, percentage conversions?

Outputs:
- strategy_qc_audit_v2.json (detailed results)
- strategy_qc_audit_v2.csv (table format)
"""

import json
import re
import csv
import sys
from typing import Dict, List, Tuple, Set

sys.path.insert(0, '/home/tiantian/keyan/pilot/stage36_paired_abstraction')
from canonical_evaluator_v2 import parse_program_v2_strict


BASE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'


def extract_operations_from_program(program: str) -> List[str]:
    """
    Extract operation names from gold program strictly.

    Returns list of operations in order.
    """
    steps, error = parse_program_v2_strict(program)

    if steps is None:
        # Parse failed - try manual extraction as fallback
        # Look for known operations
        ops = []
        for op in ['add', 'subtract', 'multiply', 'divide', 'exp', 'greater',
                   'table_max', 'table_min', 'table_sum', 'table_average']:
            if re.search(rf'\b{op}\s*\(', program):
                ops.append(op)
        return ops

    # Extract operations from parsed steps
    return [step[0] for step in steps]


def detect_scale_mentions(text: str) -> Dict[str, List[str]]:
    """
    Detect scale-related mentions in strategy text.

    Uses word-boundary regex to avoid false positives.

    Returns:
        Dict with categories of scale mentions found
    """
    findings = {
        'multiply_100': [],
        'divide_100': [],
        'percentage_conversion': [],
        'percentage_mention': []
    }

    # Pattern 1: multiply by 100 (word boundaries)
    multiply_patterns = [
        r'\*\s*100\b',
        r'multiply.*?100\b',
        r'×\s*100\b',
        r'times\s+100\b',
        r'by\s+100\b.*?(convert|percentage|percent)'
    ]

    for pattern in multiply_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            findings['multiply_100'].append(match.group())

    # Pattern 2: divide by 100
    divide_patterns = [
        r'/\s*100\b',
        r'divide.*?100\b',
        r'÷\s*100\b'
    ]

    for pattern in divide_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            findings['divide_100'].append(match.group())

    # Pattern 3: percentage conversion phrases
    conversion_patterns = [
        r'convert.*?percentage',
        r'express.*?percentage',
        r'as\s+a\s+percentage',
        r'to\s+a\s+percentage',
        r'into\s+a?\s*percentage'
    ]

    for pattern in conversion_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            findings['percentage_conversion'].append(match.group())

    # Pattern 4: general percentage mentions (for context)
    percentage_patterns = [
        r'\bpercentage\b',
        r'\bpercent\b(?!\s*change)',  # exclude "percent change" as it's structural
        r'\b%\b'
    ]

    for pattern in percentage_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            findings['percentage_mention'].append(match.group())

    return findings


def check_operation_fidelity(
    gold_ops: List[str],
    strategy_text: str,
    formula_template: str
) -> Dict:
    """
    Check if strategy mentions operations not in gold program.

    Returns:
        Dict with extra_ops, missing_ops, mismatch flag
    """
    gold_ops_set = set(gold_ops)

    # Extract operations mentioned in strategy
    strategy_ops = set()

    # Check formula template
    for op in ['add', 'subtract', 'multiply', 'divide', 'exp', 'greater',
               'table_max', 'table_min', 'table_sum', 'table_average']:
        # Word boundary match
        if re.search(rf'\b{op}\b', formula_template, re.IGNORECASE):
            strategy_ops.add(op)
        if re.search(rf'\b{op}\b', strategy_text, re.IGNORECASE):
            strategy_ops.add(op)

    # Check for arithmetic symbols
    if '+' in formula_template or 'add' in strategy_text.lower():
        strategy_ops.add('add')
    if '-' in formula_template or 'subtract' in strategy_text.lower():
        strategy_ops.add('subtract')
    if '*' in formula_template or '×' in formula_template or 'multiply' in strategy_text.lower():
        strategy_ops.add('multiply')
    if '/' in formula_template or '÷' in formula_template or 'divide' in strategy_text.lower():
        strategy_ops.add('divide')

    extra_ops = list(strategy_ops - gold_ops_set)
    missing_ops = list(gold_ops_set - strategy_ops)

    return {
        'extra_ops': extra_ops,
        'missing_ops': missing_ops,
        'operation_mismatch': len(extra_ops) > 0 or len(missing_ops) > 0
    }


def audit_source(
    source_id: str,
    case: Dict,
    strategy: Dict
) -> Dict:
    """
    Audit one source for operation and scale fidelity.
    """
    # Extract gold program operations
    gold_program = case['program']
    gold_ops = extract_operations_from_program(gold_program)

    # Get strategy text
    strategy_text = strategy['reasoning_steps']
    formula_template = strategy.get('formula_template', '')
    operand_roles = strategy.get('operand_roles', '')

    # Combined text for scale detection
    combined_text = f"{strategy_text}\n{formula_template}\n{operand_roles}"

    # Check operation fidelity
    op_fidelity = check_operation_fidelity(gold_ops, strategy_text, formula_template)

    # Check scale fidelity
    scale_mentions = detect_scale_mentions(combined_text)

    # Determine if there's scale contamination
    has_multiply_100 = len(scale_mentions['multiply_100']) > 0
    has_divide_100 = len(scale_mentions['divide_100']) > 0
    has_percentage_conversion = len(scale_mentions['percentage_conversion']) > 0

    # Check if gold program has multiply by 100
    gold_has_100 = 'const_100' in gold_program or ', 100)' in gold_program or '(100,' in gold_program

    # Scale mismatch: strategy mentions ×100 but gold doesn't have it
    scale_mismatch = (has_multiply_100 or has_percentage_conversion) and not gold_has_100

    # Build reason
    reasons = []
    if op_fidelity['operation_mismatch']:
        if op_fidelity['extra_ops']:
            reasons.append(f"Extra ops: {', '.join(op_fidelity['extra_ops'])}")
        if op_fidelity['missing_ops']:
            reasons.append(f"Missing ops: {', '.join(op_fidelity['missing_ops'])}")

    if scale_mismatch:
        if has_multiply_100:
            reasons.append(f"Spurious ×100 (gold has no const_100)")
        if has_percentage_conversion:
            reasons.append(f"Percentage conversion mention")

    reason = "; ".join(reasons) if reasons else "OK"

    return {
        'source_id': source_id,
        'gold_program': gold_program,
        'gold_ops': gold_ops,
        'gold_has_100': gold_has_100,
        'strategy_formula': formula_template,
        'strategy_reasoning': strategy_text[:200] + '...' if len(strategy_text) > 200 else strategy_text,
        'extra_ops': op_fidelity['extra_ops'],
        'missing_ops': op_fidelity['missing_ops'],
        'operation_mismatch': op_fidelity['operation_mismatch'],
        'scale_mentions': scale_mentions,
        'has_multiply_100': has_multiply_100,
        'has_divide_100': has_divide_100,
        'has_percentage_conversion': has_percentage_conversion,
        'scale_mismatch': scale_mismatch,
        'contaminated': op_fidelity['operation_mismatch'] or scale_mismatch,
        'reason': reason
    }


def main():
    """Run comprehensive Strategy QC audit."""

    print("="*80)
    print("STRATEGY QC AUDIT V2")
    print("="*80)
    print()

    # Load data
    print("Loading data...")
    with open(f'{BASE_PATH}/cases_clean.json') as f:
        cases = json.load(f)
    case_map = {c['source_experience_id']: c for c in cases}

    with open(f'{BASE_PATH}/strategies_format_neutral.json') as f:
        strategies = json.load(f)
    strategy_map = {s['source_experience_id']: s for s in strategies}

    with open(f'{BASE_PATH}/grounded_sketches.json') as f:
        sketches = json.load(f)
    sketch_map = {s['source_experience_id']: s for s in sketches}

    print(f"  Cases: {len(cases)}")
    print(f"  Strategies: {len(strategies)}")
    print(f"  Sketches: {len(sketches)}")
    print()

    # Audit each source
    print("Running audit...")
    audit_results = []

    for source_id in sorted(case_map.keys()):
        case = case_map[source_id]

        if source_id not in strategy_map:
            print(f"  ⚠️  {source_id}: No strategy found")
            continue

        strategy = strategy_map[source_id]

        result = audit_source(source_id, case, strategy)
        audit_results.append(result)

        # Print immediate findings
        if result['contaminated']:
            print(f"  ❌ {source_id}: {result['reason']}")

    print()

    # Compute statistics
    total = len(audit_results)
    operation_mismatches = sum(1 for r in audit_results if r['operation_mismatch'])
    scale_mismatches = sum(1 for r in audit_results if r['scale_mismatch'])
    contaminated = sum(1 for r in audit_results if r['contaminated'])

    # Specific check: E002
    e002_result = next((r for r in audit_results if r['source_id'] == 'E002'), None)

    print("="*80)
    print("STATISTICS")
    print("="*80)
    print(f"Total sources:           {total}")
    print(f"Operation mismatches:    {operation_mismatches} ({100*operation_mismatches/total:.1f}%)")
    print(f"Scale mismatches:        {scale_mismatches} ({100*scale_mismatches/total:.1f}%)")
    print(f"Total contaminated:      {contaminated} ({100*contaminated/total:.1f}%)")
    print()

    if e002_result:
        print("E002 SPECIFIC CHECK:")
        print(f"  Gold program: {e002_result['gold_program']}")
        print(f"  Gold has const_100: {e002_result['gold_has_100']}")
        print(f"  Strategy formula: {e002_result['strategy_formula']}")
        print(f"  Has ×100 mention: {e002_result['has_multiply_100']}")
        print(f"  Has percentage conversion: {e002_result['has_percentage_conversion']}")
        print(f"  Scale mismatch: {e002_result['scale_mismatch']}")
        print(f"  Status: {'❌ CONTAMINATED' if e002_result['contaminated'] else '✓ CLEAN'}")
        print()

    # List contaminated sources
    contaminated_sources = [r for r in audit_results if r['contaminated']]
    if contaminated_sources:
        print("CONTAMINATED SOURCES:")
        for r in contaminated_sources[:20]:
            print(f"  {r['source_id']}: {r['reason']}")
        if len(contaminated_sources) > 20:
            print(f"  ... and {len(contaminated_sources) - 20} more")
        print()

    # Save JSON
    output = {
        'audit_results': audit_results,
        'statistics': {
            'total': total,
            'operation_mismatches': operation_mismatches,
            'scale_mismatches': scale_mismatches,
            'contaminated': contaminated,
            'contamination_rate': contaminated / total if total > 0 else 0.0
        },
        'e002_check': e002_result,
        'note': 'Comprehensive QC with operation and scale fidelity checks'
    }

    output_json = f'{BASE_PATH}/strategy_qc_audit_v2.json'
    with open(output_json, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Saved: {output_json}")

    # Save CSV
    output_csv = f'{BASE_PATH}/strategy_qc_audit_v2.csv'
    with open(output_csv, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'source_id', 'gold_program', 'gold_ops', 'gold_has_100',
            'strategy_formula', 'extra_ops', 'missing_ops',
            'operation_mismatch', 'has_multiply_100', 'has_divide_100',
            'has_percentage_conversion', 'scale_mismatch', 'contaminated', 'reason'
        ])
        writer.writeheader()

        for r in audit_results:
            writer.writerow({
                'source_id': r['source_id'],
                'gold_program': r['gold_program'],
                'gold_ops': ', '.join(r['gold_ops']),
                'gold_has_100': r['gold_has_100'],
                'strategy_formula': r['strategy_formula'],
                'extra_ops': ', '.join(r['extra_ops']),
                'missing_ops': ', '.join(r['missing_ops']),
                'operation_mismatch': r['operation_mismatch'],
                'has_multiply_100': r['has_multiply_100'],
                'has_divide_100': r['has_divide_100'],
                'has_percentage_conversion': r['has_percentage_conversion'],
                'scale_mismatch': r['scale_mismatch'],
                'contaminated': r['contaminated'],
                'reason': r['reason']
            })

    print(f"Saved: {output_csv}")
    print("="*80)


if __name__ == '__main__':
    main()
