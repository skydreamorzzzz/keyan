#!/usr/bin/env python3
"""
Faithful Abstraction QC

Strict structural validation to ensure execution fidelity.

Checks:
1. Operation mentions match gold program operations exactly
2. Scale convention matches gold program (×100 presence/absence)
3. No spurious operations mentioned
4. No missing operations
5. No executable templates/sketches
"""

import json
import re
import sys
from typing import Dict, List, Set

BASE_PATH = '/home/tiantian/keyan/pilot/stage41_abstraction_fidelity'


def extract_operation_mentions(text: str) -> Set[str]:
    """
    Extract operation mentions from natural language text.

    Uses strict word-boundary matching to avoid false positives.
    """
    operations = {
        'add', 'subtract', 'multiply', 'divide', 'exp', 'greater',
        'table_max', 'table_min', 'table_sum', 'table_average'
    }

    mentioned = set()

    text_lower = text.lower()

    for op in operations:
        # Word boundary match
        if re.search(rf'\b{op}\b', text_lower):
            mentioned.add(op)

    # Also check for operation synonyms
    if re.search(r'\b(sum|total|add up|combine)\b', text_lower) and 'add' not in mentioned:
        # Check if gold has 'add'
        pass  # Will be checked against gold

    if re.search(r'\b(difference|minus|deduct)\b', text_lower) and 'subtract' not in mentioned:
        pass

    if re.search(r'\b(product|times|×)\b', text_lower) and 'multiply' not in mentioned:
        pass

    if re.search(r'\b(quotient|ratio|÷)\b', text_lower) and 'divide' not in mentioned:
        mentioned.add('divide')  # Common case

    return mentioned


def check_scale_mentions(text: str) -> Dict:
    """Check for scale-related mentions."""

    findings = {
        'has_multiply_100': False,
        'has_divide_100': False,
        'has_percentage_conversion': False,
        'has_decimal_mention': False
    }

    text_lower = text.lower()

    # Multiply by 100
    if re.search(r'(\*|×|multiply.*?by)\s*100\b', text_lower):
        findings['has_multiply_100'] = True

    if re.search(r'(times\s+100|by\s+100)', text_lower):
        findings['has_multiply_100'] = True

    # Divide by 100
    if re.search(r'(/|÷|divide.*?by)\s*100\b', text_lower):
        findings['has_divide_100'] = True

    # Percentage conversion phrases
    if re.search(r'(convert.*?to.*?percentage|express.*?as.*?percentage|percentage.*?conversion)', text_lower):
        findings['has_percentage_conversion'] = True

    # Decimal/ratio mentions
    if re.search(r'\b(decimal|ratio|proportion)\b', text_lower):
        findings['has_decimal_mention'] = True

    return findings


def check_template_leakage(abstraction: Dict) -> bool:
    """Check if abstraction contains executable templates."""

    # Check all text fields
    all_text = ' '.join([
        abstraction.get('strategy_name', ''),
        abstraction.get('problem_pattern', ''),
        abstraction.get('reasoning_steps', ''),
        abstraction.get('operand_roles', ''),
        abstraction.get('units_convention', '')
    ])

    # Look for FinQA syntax patterns
    if re.search(r'<value\d+>', all_text):
        return True

    if re.search(r'(add|subtract|multiply|divide)\s*\([^)]*\)', all_text):
        return True

    if re.search(r'#\d+', all_text):
        return True

    return False


def qc_abstraction(abstraction: Dict) -> Dict:
    """
    QC one abstraction for execution fidelity.

    Returns QC result with pass/fail and reasons.
    """
    source_id = abstraction['source_experience_id']
    gold_struct = abstraction['gold_structure']
    gold_ops = set(gold_struct['operations'])
    gold_has_100 = gold_struct['has_scale_100']

    # Extract all text
    all_text = ' '.join([
        abstraction.get('reasoning_steps', ''),
        abstraction.get('operand_roles', ''),
        abstraction.get('units_convention', '')
    ])

    # Check operation mentions
    mentioned_ops = extract_operation_mentions(all_text)

    extra_ops = mentioned_ops - gold_ops
    missing_ops = gold_ops - mentioned_ops

    # Check scale mentions
    scale_findings = check_scale_mentions(all_text)

    # Check template leakage
    has_template = check_template_leakage(abstraction)

    # Determine issues
    issues = []

    if extra_ops:
        issues.append(f"extra_ops: {', '.join(extra_ops)}")

    if missing_ops:
        issues.append(f"missing_ops: {', '.join(missing_ops)}")

    # Scale fidelity check
    if gold_has_100:
        # Gold has ×100, abstraction should mention it
        if not scale_findings['has_multiply_100'] and not scale_findings['has_percentage_conversion']:
            issues.append("missing_scale_100: gold has ×100 but abstraction doesn't mention it")
    else:
        # Gold has no ×100, abstraction should NOT mention it
        if scale_findings['has_multiply_100'] or scale_findings['has_percentage_conversion']:
            issues.append("spurious_scale_100: gold has no ×100 but abstraction mentions percentage conversion")

    if has_template:
        issues.append("template_leakage: contains executable template syntax")

    # Determine pass/fail
    passed = len(issues) == 0

    return {
        'source_id': source_id,
        'gold_operations': list(gold_ops),
        'mentioned_operations': list(mentioned_ops),
        'gold_has_100': gold_has_100,
        'scale_findings': scale_findings,
        'extra_ops': list(extra_ops),
        'missing_ops': list(missing_ops),
        'has_template': has_template,
        'issues': issues,
        'passed': passed,
        'reason': '; '.join(issues) if issues else 'OK'
    }


def main():
    """Run faithful abstraction QC."""

    print("="*80)
    print("FAITHFUL ABSTRACTION QC")
    print("="*80)
    print()

    # Load abstractions
    with open(f'{BASE_PATH}/faithful_abstractions_raw.json') as f:
        abstractions = json.load(f)

    print(f"Loaded {len(abstractions)} abstractions")
    print()

    # QC each abstraction
    print("Running structural QC...")
    print()

    qc_results = []

    for abstraction in abstractions:
        result = qc_abstraction(abstraction)
        qc_results.append(result)

        if not result['passed']:
            print(f"  ❌ {result['source_id']}: {result['reason']}")

    print()

    # Statistics
    total = len(qc_results)
    passed = sum(1 for r in qc_results if r['passed'])
    failed = total - passed

    operation_issues = sum(1 for r in qc_results if r['extra_ops'] or r['missing_ops'])
    scale_issues = sum(1 for r in qc_results if 'scale' in r['reason'].lower())
    template_issues = sum(1 for r in qc_results if r['has_template'])

    print("="*80)
    print("QC STATISTICS")
    print("="*80)
    print(f"Total:             {total}")
    print(f"Passed:            {passed} ({100*passed/total:.1f}%)")
    print(f"Failed:            {failed} ({100*failed/total:.1f}%)")
    print(f"Operation issues:  {operation_issues}")
    print(f"Scale issues:      {scale_issues}")
    print(f"Template issues:   {template_issues}")
    print()

    if failed > 0:
        print("Failed abstractions:")
        failed_results = [r for r in qc_results if not r['passed']]
        for r in failed_results[:20]:
            print(f"  {r['source_id']}: {r['reason']}")
        if len(failed_results) > 20:
            print(f"  ... and {len(failed_results) - 20} more")
        print()

    # Save QC results
    output = {
        'qc_results': qc_results,
        'statistics': {
            'total': total,
            'passed': passed,
            'failed': failed,
            'pass_rate': passed / total if total > 0 else 0,
            'operation_issues': operation_issues,
            'scale_issues': scale_issues,
            'template_issues': template_issues
        },
        'note': 'Structural QC for execution fidelity'
    }

    output_file = f'{BASE_PATH}/faithful_abstraction_qc.json'
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Saved: {output_file}")
    print()

    # Decision
    if passed == total:
        print("✓ All abstractions passed QC")
        print()
        print("Next: Build corruption manifest")
        print("  python3 build_corruption_manifest.py")
        return True
    else:
        threshold = 0.9  # 90% pass rate required
        if passed / total >= threshold:
            print(f"⚠️  {100*passed/total:.1f}% passed (>= {100*threshold:.0f}% threshold)")
            print("Acceptable for proceeding, but review failures")
            print()
            print("Next: Filter to passed abstractions and build corruption manifest")
            return True
        else:
            print(f"✗ Only {100*passed/total:.1f}% passed (< {100*threshold:.0f}% threshold)")
            print("Too many failures - need to regenerate or fix")
            return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
