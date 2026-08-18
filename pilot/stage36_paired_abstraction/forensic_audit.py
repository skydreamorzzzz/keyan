#!/usr/bin/env python3
"""
Strategy Failure Forensic Audit

Analyzes Stage 37 raw responses to understand why Strategy collapsed.

Focus areas:
1. Strategy parse-success + exec-fail cases (why do programs fail?)
2. Strategy rescues (when does Strategy help?)
3. Strategy harms (when does Strategy hurt?)
4. Case rescues (what patterns does Case capture?)
5. Case/Strategy disagreements (what differs between concrete and abstract?)

Output: Failure taxonomy and mechanism analysis
"""

import json
import sys
import re
from collections import defaultdict, Counter

# Import FinQA official executor
sys.path.insert(0, '/home/tiantian/keyan/pilot')
from executor import parse_program_re, parse_linear_steps, exec_steps

BASE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'

def load_data():
    """Load all audit data."""

    # Load audit records
    with open(f'{BASE_PATH}/expanded_audit_canonical.json') as f:
        audit_records = json.load(f)

    # Load transitions
    with open(f'{BASE_PATH}/expanded_audit_transitions.json') as f:
        transitions = json.load(f)

    # Load raw responses
    arms_data = {}
    for arm in ['none', 'case', 'strategy', 'paired']:
        with open(f'{BASE_PATH}/results_{arm}_expanded.json') as f:
            responses = json.load(f)
            # Build lookup by target_id
            arms_data[arm] = {r['target_id']: r for r in responses}

    # Load targets
    with open(f'{BASE_PATH}/expanded_sample_queries.json') as f:
        targets = json.load(f)
        target_lookup = {t['id']: t for t in targets}

    return audit_records, transitions, arms_data, target_lookup


def build_audit_matrix(audit_records):
    """Build target_id -> arm -> record lookup."""
    matrix = defaultdict(dict)
    for record in audit_records:
        target_id = record['target_id']
        arm = record['arm']
        matrix[target_id][arm] = record
    return matrix


def extract_failure_type(record, raw_response):
    """Classify failure type for a single record."""

    exec_status = record['execution_status']
    raw_program = record['raw_program']
    normalized_program = record['normalized_program']
    program_correct = record['program_correct']

    # Success cases
    if program_correct:
        return 'success'

    # No program line
    if not raw_program:
        return 'no_program_line'

    # Empty after normalization
    if not normalized_program:
        return 'empty_after_normalization'

    # Parse failure
    if exec_status == 'parse_fail':
        return 'parse_fail'

    # Execution failure
    if exec_status == 'exec_fail':
        # Try to get more specific failure type
        return classify_exec_failure(normalized_program, raw_response)

    # Wrong result (program executes but gets wrong answer)
    if exec_status == 'success':
        return 'wrong_result'

    return 'unknown'


def classify_exec_failure(program, raw_response):
    """Further classify execution failures."""

    # Check for table operations
    if 'table_' in program:
        return 'exec_fail_table_op'

    # Check for invalid intermediate references
    if re.search(r'#\d+', program):
        # Count intermediate refs
        refs = re.findall(r'#(\d+)', program)
        max_ref = max([int(r) for r in refs]) if refs else -1

        # Count operations before the ref
        ops = program.split(',')
        if max_ref >= len(ops):
            return 'exec_fail_invalid_ref'

    # Check for malformed syntax
    if not re.match(r'^[a-z_]+\(', program):
        return 'exec_fail_malformed_syntax'

    # Generic execution failure
    return 'exec_fail_other'


def analyze_strategy_parse_exec_fail():
    """Analyze Strategy cases that parse successfully but fail execution."""

    print("=" * 80)
    print("STRATEGY PARSE-SUCCESS + EXEC-FAIL ANALYSIS")
    print("=" * 80)
    print()

    audit_records, transitions, arms_data, target_lookup = load_data()
    matrix = build_audit_matrix(audit_records)

    # Find Strategy parse-success + exec-fail cases
    strategy_parse_exec_fail = []

    for target_id, arms in matrix.items():
        strategy_record = arms.get('strategy')
        if not strategy_record:
            continue

        if (strategy_record['normalized_program'] is not None and
            strategy_record['execution_status'] == 'exec_fail'):

            strategy_parse_exec_fail.append({
                'target_id': target_id,
                'record': strategy_record,
                'raw_response': arms_data['strategy'][target_id]['response']
            })

    print(f"Total Strategy parse-success + exec-fail: {len(strategy_parse_exec_fail)}/224")
    print()

    # Classify failure types
    failure_types = Counter()
    failure_examples = defaultdict(list)

    for item in strategy_parse_exec_fail:
        target_id = item['target_id']
        record = item['record']
        raw_response = item['raw_response']

        failure_type = classify_exec_failure(
            record['normalized_program'],
            raw_response
        )

        failure_types[failure_type] += 1

        # Keep examples (max 3 per type)
        if len(failure_examples[failure_type]) < 3:
            failure_examples[failure_type].append({
                'target_id': target_id,
                'program': record['normalized_program'],
                'gold': record['gold_answer']
            })

    print("Failure Type Distribution:")
    print("-" * 80)
    for ftype, count in failure_types.most_common():
        pct = 100.0 * count / len(strategy_parse_exec_fail)
        print(f"{ftype:30s}: {count:3d} ({pct:5.1f}%)")

    print()
    print("Examples by Failure Type:")
    print("-" * 80)

    for ftype in failure_types.most_common():
        ftype_name = ftype[0]
        print(f"\n### {ftype_name}")
        for ex in failure_examples[ftype_name][:3]:
            print(f"  {ex['target_id']}")
            print(f"    Program: {ex['program']}")
            print(f"    Gold: {ex['gold']}")

    return strategy_parse_exec_fail, failure_types, failure_examples


def analyze_rescues_and_harms():
    """Analyze rescue and harm patterns."""

    print("\n")
    print("=" * 80)
    print("RESCUE & HARM ANALYSIS")
    print("=" * 80)
    print()

    audit_records, transitions, arms_data, target_lookup = load_data()
    matrix = build_audit_matrix(audit_records)

    # Strategy rescues
    strategy_rescues = transitions['strategy_rescues']
    print(f"Strategy Rescues: {len(strategy_rescues)}/224 ({100.0*len(strategy_rescues)/224:.1f}%)")
    print("-" * 80)

    for target_id in strategy_rescues[:10]:
        none_rec = matrix[target_id]['none']
        strategy_rec = matrix[target_id]['strategy']

        print(f"\n{target_id}")
        print(f"  None: {none_rec['execution_status']} → {none_rec['execution_result']}")
        print(f"  Strategy: {strategy_rec['execution_status']} → {strategy_rec['execution_result']}")
        print(f"  Gold: {strategy_rec['gold_answer']}")

    # Strategy harms
    strategy_harms = transitions['strategy_harms']
    print(f"\n\nStrategy Harms: {len(strategy_harms)}/224 ({100.0*len(strategy_harms)/224:.1f}%)")
    print("-" * 80)

    for target_id in strategy_harms[:10]:
        none_rec = matrix[target_id]['none']
        strategy_rec = matrix[target_id]['strategy']

        print(f"\n{target_id}")
        print(f"  None: {none_rec['execution_status']} → {none_rec['execution_result']}")
        print(f"  Strategy: {strategy_rec['execution_status']} → {strategy_rec['execution_result']}")
        print(f"  Gold: {strategy_rec['gold_answer']}")

    # Case rescues
    case_rescues = transitions['case_rescues']
    print(f"\n\nCase Rescues: {len(case_rescues)}/224 ({100.0*len(case_rescues)/224:.1f}%)")
    print("-" * 80)

    for target_id in case_rescues[:10]:
        none_rec = matrix[target_id]['none']
        case_rec = matrix[target_id]['case']

        print(f"\n{target_id}")
        print(f"  None: {none_rec['execution_status']} → {none_rec['execution_result']}")
        print(f"  Case: {case_rec['execution_status']} → {case_rec['execution_result']}")
        print(f"  Gold: {case_rec['gold_answer']}")

    return {
        'strategy_rescues': strategy_rescues,
        'strategy_harms': strategy_harms,
        'case_rescues': case_rescues
    }


def analyze_case_strategy_disagreement():
    """Analyze queries where Case and Strategy disagree."""

    print("\n")
    print("=" * 80)
    print("CASE vs STRATEGY DISAGREEMENT")
    print("=" * 80)
    print()

    audit_records, transitions, arms_data, target_lookup = load_data()
    matrix = build_audit_matrix(audit_records)

    # Find disagreements
    disagreements = []

    for target_id, arms in matrix.items():
        case_rec = arms.get('case')
        strategy_rec = arms.get('strategy')

        if not case_rec or not strategy_rec:
            continue

        case_correct = case_rec['program_correct']
        strategy_correct = strategy_rec['program_correct']

        if case_correct != strategy_correct:
            disagreements.append({
                'target_id': target_id,
                'case_correct': case_correct,
                'strategy_correct': strategy_correct,
                'case_status': case_rec['execution_status'],
                'strategy_status': strategy_rec['execution_status']
            })

    print(f"Total Disagreements: {len(disagreements)}/224 ({100.0*len(disagreements)/224:.1f}%)")
    print()

    # Count patterns
    case_wins = [d for d in disagreements if d['case_correct'] and not d['strategy_correct']]
    strategy_wins = [d for d in disagreements if not d['case_correct'] and d['strategy_correct']]

    print(f"Case correct, Strategy wrong: {len(case_wins)}")
    print(f"Strategy correct, Case wrong: {len(strategy_wins)}")
    print()

    print("Case Wins (first 10):")
    print("-" * 80)
    for d in case_wins[:10]:
        print(f"  {d['target_id']}: Case {d['case_status']}, Strategy {d['strategy_status']}")

    print()
    print("Strategy Wins (all):")
    print("-" * 80)
    for d in strategy_wins:
        print(f"  {d['target_id']}: Case {d['case_status']}, Strategy {d['strategy_status']}")

    return disagreements, case_wins, strategy_wins


def main():
    """Run complete forensic audit."""

    # Part 1: Strategy parse-exec-fail analysis
    parse_exec_fail_data = analyze_strategy_parse_exec_fail()

    # Part 2: Rescues and harms
    rescue_harm_data = analyze_rescues_and_harms()

    # Part 3: Case vs Strategy disagreement
    disagreement_data = analyze_case_strategy_disagreement()

    print("\n")
    print("=" * 80)
    print("FORENSIC AUDIT COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    main()
