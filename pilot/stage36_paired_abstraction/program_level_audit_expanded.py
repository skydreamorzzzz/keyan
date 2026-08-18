#!/usr/bin/env python3
"""
Stage 37 Expanded Program-Level Audit

This script adapts the Stage 36 audit to handle the 224-query expanded sample.

Input:
- expanded_sample_queries.json (224 targets: 30 pilot + 194 new)
- results_none_expanded.json (224 responses)
- results_case_expanded.json (224 responses)
- results_strategy_expanded.json (224 responses)
- results_paired_expanded.json (224 responses)

Output:
- expanded_audit_canonical.json (896 records)
- expanded_audit_summary.json (per-arm statistics)
- expanded_audit_transitions.json (rescue/harm analysis)
- expanded_stability_report.json (pilot vs expanded comparison)
"""

import json
import sys
import re
import os
from typing import Dict, List, Any, Optional, Tuple

# Import FinQA official executor
sys.path.insert(0, '/home/tiantian/keyan/pilot')
from executor import parse_program_re, parse_linear_steps, exec_steps, official_normalize_result, match_result

# Import functions from original audit script
sys.path.insert(0, '/home/tiantian/keyan/pilot/stage36_paired_abstraction')
from program_level_audit import (
    extract_answer_from_response,
    extract_program_from_response,
    normalize_program,
    execute_program_with_table
)

def audit_expanded_sample():
    """Main audit for 224-query expanded sample."""

    BASE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'

    print("=" * 80)
    print("STAGE 37 EXPANDED PROGRAM-LEVEL AUDIT")
    print("=" * 80)
    print()

    # Load expanded sample (224 targets)
    print("[1/6] Loading expanded sample...")
    with open(os.path.join(BASE_PATH, 'expanded_sample_queries.json'), 'r') as f:
        targets = json.load(f)

    target_lookup = {t['id']: t for t in targets}
    canonical_ids = set(target_lookup.keys())
    print(f"  Loaded {len(targets)} targets")

    # Count pilot vs new
    pilot_count = sum(1 for t in targets if t.get('is_pilot', False))
    print(f"    Pilot: {pilot_count}")
    print(f"    New: {len(targets) - pilot_count}")
    print()

    # Load all arm results
    print("[2/6] Loading arm results...")
    arms = ['none', 'case', 'strategy', 'paired']
    arm_data = {}

    for arm in arms:
        fpath = os.path.join(BASE_PATH, f'results_{arm}_expanded.json')
        with open(fpath, 'r') as f:
            arm_data[arm] = json.load(f)
        print(f"  {arm}: {len(arm_data[arm])} responses")

    print()

    # Validation
    print("[3/6] Validating input consistency...")
    for arm in arms:
        count = len(arm_data[arm])
        assert count == 224, f"{arm} has {count} responses, expected 224"

        arm_ids = set([r['target_id'] for r in arm_data[arm]])
        assert arm_ids == canonical_ids, f"{arm} target IDs do not match canonical set"

        # Check for duplicates
        target_ids = [r['target_id'] for r in arm_data[arm]]
        assert len(target_ids) == len(set(target_ids)), f"{arm} has duplicate target_ids"

    print("  ✓ All assertions passed")
    print()

    # Build audit matrix
    print("[4/6] Executing program-level audit...")
    audit_records = []

    for arm in arms:
        for response_data in arm_data[arm]:
            target_id = response_data['target_id']
            target = target_lookup[target_id]

            # Extract program
            raw_program = extract_program_from_response(response_data['response'])
            normalized_program = normalize_program(raw_program) if raw_program else None

            # Execute program with table
            if normalized_program:
                table = target.get('table', None)
                exec_result, exec_status = execute_program_with_table(normalized_program, table)
            else:
                exec_result = None
                exec_status = 'no_program'

            # Extract answer
            predicted_answer = extract_answer_from_response(response_data['response'])

            # Check program correctness
            gold_result = target['qa'].get('exe_ans')
            if gold_result is None:
                gold_result = target['qa']['answer']

            program_correct = False
            if exec_status == 'success' and exec_result is not None:
                try:
                    program_correct = match_result(exec_result, gold_result)
                except:
                    program_correct = False

            # Determine failure reason
            failure_reason = None
            if not program_correct:
                if not raw_program:
                    failure_reason = 'no_program_line'
                elif not normalized_program:
                    failure_reason = 'empty_after_normalization'
                elif exec_status == 'parse_fail':
                    failure_reason = 'parse_failure'
                elif exec_status == 'exec_fail':
                    failure_reason = 'execution_failure'
                elif exec_status == 'success':
                    failure_reason = 'wrong_result'

            # Strict answer-level evaluation
            strict_answer_correct = False
            if predicted_answer is not None:
                try:
                    strict_answer_correct = match_result(predicted_answer, gold_result)
                except:
                    strict_answer_correct = False

            # Build record
            record = {
                'target_id': target_id,
                'arm': arm,
                'gold_answer': gold_result,
                'raw_program': raw_program,
                'normalized_program': normalized_program,
                'execution_status': exec_status,
                'execution_result': exec_result,
                'program_correct': program_correct,
                'failure_reason': failure_reason,
                'parsed_answer': predicted_answer,
                'strict_answer_correct': strict_answer_correct,
                'shared_source_ids': response_data.get('shared_source_ids', []),
                'is_pilot': target.get('is_pilot', False)
            }

            audit_records.append(record)

    print(f"  Processed {len(audit_records)} records")
    print()

    # Compute summary statistics
    print("[5/6] Computing summary statistics...")

    summary = {}
    for arm in arms:
        arm_records = [r for r in audit_records if r['arm'] == arm]

        summary[arm] = {
            'total': len(arm_records),
            'program_correct': sum(1 for r in arm_records if r['program_correct']),
            'strict_answer_correct': sum(1 for r in arm_records if r['strict_answer_correct']),
            'parsed': sum(1 for r in arm_records if r['normalized_program'] is not None),
            'executed': sum(1 for r in arm_records if r['execution_status'] == 'success')
        }

    print()

    # Analyze transitions
    print("[6/6] Analyzing transitions...")

    # Build outcome matrix: target_id -> {arm: program_correct}
    outcome_matrix = {}
    for record in audit_records:
        target_id = record['target_id']
        arm = record['arm']
        if target_id not in outcome_matrix:
            outcome_matrix[target_id] = {}
        outcome_matrix[target_id][arm] = record['program_correct']

    # Classify transitions
    invariant_correct = []
    invariant_wrong = []
    case_rescues = []
    strategy_rescues = []
    paired_rescues = []
    case_harms = []
    strategy_harms = []
    paired_harms = []

    for target_id, outcomes in outcome_matrix.items():
        none_correct = outcomes.get('none', False)
        case_correct = outcomes.get('case', False)
        strategy_correct = outcomes.get('strategy', False)
        paired_correct = outcomes.get('paired', False)

        # Invariant patterns
        if none_correct and case_correct and strategy_correct and paired_correct:
            invariant_correct.append(target_id)
            continue
        elif not none_correct and not case_correct and not strategy_correct and not paired_correct:
            invariant_wrong.append(target_id)
            continue

        # Rescues and harms
        if not none_correct and case_correct:
            case_rescues.append(target_id)
        if none_correct and not case_correct:
            case_harms.append(target_id)

        if not none_correct and strategy_correct:
            strategy_rescues.append(target_id)
        if none_correct and not strategy_correct:
            strategy_harms.append(target_id)

        if not none_correct and paired_correct:
            paired_rescues.append(target_id)
        if none_correct and not paired_correct:
            paired_harms.append(target_id)

    transitions = {
        'invariant_correct': invariant_correct,
        'invariant_correct_count': len(invariant_correct),
        'invariant_wrong': invariant_wrong,
        'invariant_wrong_count': len(invariant_wrong),
        'case_rescues': case_rescues,
        'strategy_rescues': strategy_rescues,
        'paired_rescues': paired_rescues,
        'case_harms': case_harms,
        'strategy_harms': strategy_harms,
        'paired_harms': paired_harms,
        'memory_sensitive_count': len(target_lookup) - len(invariant_correct) - len(invariant_wrong)
    }

    print()

    # Save outputs
    print("Saving outputs...")

    output_files = {
        'canonical': os.path.join(BASE_PATH, 'expanded_audit_canonical.json'),
        'summary': os.path.join(BASE_PATH, 'expanded_audit_summary.json'),
        'transitions': os.path.join(BASE_PATH, 'expanded_audit_transitions.json')
    }

    with open(output_files['canonical'], 'w') as f:
        json.dump(audit_records, f, indent=2)
    print(f"  ✓ {os.path.basename(output_files['canonical'])}")

    with open(output_files['summary'], 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"  ✓ {os.path.basename(output_files['summary'])}")

    with open(output_files['transitions'], 'w') as f:
        json.dump(transitions, f, indent=2)
    print(f"  ✓ {os.path.basename(output_files['transitions'])}")

    print()

    # Print summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()

    print("Program-Level Accuracy:")
    print("-" * 40)
    for arm in arms:
        arm_summary = summary[arm]
        correct = arm_summary['program_correct']
        total = arm_summary['total']
        pct = 100.0 * correct / total if total > 0 else 0
        print(f"{arm:10s}: {correct:3d}/{total} ({pct:5.1f}%)")

    print()
    print("Strict Answer-Level Accuracy:")
    print("-" * 40)
    for arm in arms:
        arm_summary = summary[arm]
        correct = arm_summary['strict_answer_correct']
        total = arm_summary['total']
        pct = 100.0 * correct / total if total > 0 else 0
        print(f"{arm:10s}: {correct:3d}/{total} ({pct:5.1f}%)")

    print()
    print("Coverage:")
    print("-" * 40)
    for arm in arms:
        arm_summary = summary[arm]
        parsed = arm_summary['parsed']
        executed = arm_summary['executed']
        total = arm_summary['total']
        print(f"{arm:10s}: parsed {parsed}/{total}, executed {executed}/{total}")

    print()
    print("Transitions:")
    print("-" * 40)
    print(f"Invariant correct (4/4 arms): {transitions['invariant_correct_count']:3d}/{len(target_lookup)}")
    print(f"Invariant wrong (0/4 arms):   {transitions['invariant_wrong_count']:3d}/{len(target_lookup)}")
    print(f"Case rescues:                 {len(transitions['case_rescues']):3d}/{len(target_lookup)}")
    print(f"Strategy rescues:             {len(transitions['strategy_rescues']):3d}/{len(target_lookup)}")
    print(f"Paired rescues:               {len(transitions['paired_rescues']):3d}/{len(target_lookup)}")
    print(f"Case harms:                   {len(transitions['case_harms']):3d}/{len(target_lookup)}")
    print(f"Strategy harms:               {len(transitions['strategy_harms']):3d}/{len(target_lookup)}")
    print(f"Paired harms:                 {len(transitions['paired_harms']):3d}/{len(target_lookup)}")

    print()
    print("=" * 80)
    print("✓ Expanded audit complete")
    print("=" * 80)

    return audit_records, summary, transitions


if __name__ == '__main__':
    audit_expanded_sample()
