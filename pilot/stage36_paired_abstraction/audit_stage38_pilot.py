#!/usr/bin/env python3
"""
Stage 38 Pilot Audit: Evaluate format confound test results.
"""
import json
import sys
import re

sys.path.insert(0, '/home/tiantian/keyan/pilot')
from executor import parse_program_re, parse_linear_steps, exec_steps

def audit_response(response_record, target_map):
    """Audit single response."""
    target_id = response_record['target_id']
    target = target_map[target_id]
    gold_answer = target['qa']['exe_ans']

    response_text = response_record['response']

    # Parse program
    program_match = re.search(r'PROGRAM:\s*(.+?)(?=\n|ANSWER:|$)', response_text, re.DOTALL)

    if not program_match:
        return {
            'target_id': target_id,
            'arm': response_record.get('arm', 'unknown'),
            'gold_answer': gold_answer,
            'raw_program': None,
            'normalized_program': None,
            'execution_status': 'no_program',
            'execution_result': None,
            'program_correct': False
        }

    raw_program = program_match.group(1).strip()

    # Check for operator-only pattern
    if re.match(r'^[a-z_]+(?:\s*,\s*[a-z_]+)*\s*$', raw_program):
        return {
            'target_id': target_id,
            'arm': response_record.get('arm', 'unknown'),
            'gold_answer': gold_answer,
            'raw_program': raw_program,
            'normalized_program': raw_program,
            'execution_status': 'operator_only',
            'execution_result': None,
            'program_correct': False
        }

    # Normalize program
    normalized = raw_program.replace('\n', ', ')

    # Try to parse and execute
    try:
        parsed_steps = parse_program_re(normalized)

        if not parsed_steps:
            return {
                'target_id': target_id,
                'arm': response_record.get('arm', 'unknown'),
                'gold_answer': gold_answer,
                'raw_program': raw_program,
                'normalized_program': normalized,
                'execution_status': 'parse_fail',
                'execution_result': None,
                'program_correct': False
            }

        # Try execution
        try:
            linear_steps = parse_linear_steps(parsed_steps)
            result = exec_steps(linear_steps, target)

            # Compare with gold
            correct = abs(float(result) - float(gold_answer)) < 1e-4

            return {
                'target_id': target_id,
                'arm': response_record.get('arm', 'unknown'),
                'gold_answer': gold_answer,
                'raw_program': raw_program,
                'normalized_program': normalized,
                'execution_status': 'success',
                'execution_result': result,
                'program_correct': correct
            }

        except Exception as e:
            return {
                'target_id': target_id,
                'arm': response_record.get('arm', 'unknown'),
                'gold_answer': gold_answer,
                'raw_program': raw_program,
                'normalized_program': normalized,
                'execution_status': 'exec_fail',
                'execution_result': None,
                'program_correct': False
            }

    except Exception as e:
        return {
            'target_id': target_id,
            'arm': response_record.get('arm', 'unknown'),
            'gold_answer': gold_answer,
            'raw_program': raw_program,
            'normalized_program': normalized,
            'execution_status': 'parse_fail',
            'execution_result': None,
            'program_correct': False
        }

def main():
    # Load pilot sample - it's stratified by category
    with open('stage38_pilot_sample.json') as f:
        sample_by_strata = json.load(f)

    # Flatten to get all targets
    all_targets = []
    for stratum in sample_by_strata.values():
        all_targets.extend(stratum)

    target_map = {t['id']: t for t in all_targets}

    print(f"Loaded {len(all_targets)} pilot targets")

    with open('results_format_neutral_strategy_pilot.json') as f:
        fn_results = json.load(f)

    with open('results_grounded_sketch_pilot.json') as f:
        gs_results = json.load(f)

    # Also load old Strategy for comparison
    with open('results_strategy_expanded.json') as f:
        old_strategy_all = json.load(f)
        old_strategy_map = {r['target_id']: r for r in old_strategy_all}

    # Also load Case for comparison
    with open('results_case_expanded.json') as f:
        case_all = json.load(f)
        case_map = {r['target_id']: r for r in case_all}

    # Audit all arms
    print("Auditing Format-Neutral Strategy...")
    fn_audit = [audit_response(r, target_map) for r in fn_results]

    print("Auditing Grounded Sketch...")
    gs_audit = [audit_response(r, target_map) for r in gs_results]

    print("Extracting Old Strategy pilot subset...")
    old_strategy_pilot = [old_strategy_map[tid] for tid in target_map.keys() if tid in old_strategy_map]

    print("Auditing Old Strategy pilot subset...")
    old_audit = [audit_response(r, target_map) for r in old_strategy_pilot]

    print("Extracting Case pilot subset...")
    case_pilot = [case_map[tid] for tid in target_map.keys() if tid in case_map]

    print("Auditing Case pilot subset...")
    case_audit = [audit_response(r, target_map) for r in case_pilot]

    # Save audits
    with open('stage38_pilot_audit.json', 'w') as f:
        json.dump({
            'format_neutral_strategy': fn_audit,
            'grounded_sketch': gs_audit,
            'old_strategy': old_audit,
            'case': case_audit
        }, f, indent=2)

    print("\n" + "="*80)
    print("STAGE 38 PILOT AUDIT SUMMARY")
    print("="*80)

    # Metrics
    for arm_name, audit_list in [
        ('Old Strategy', old_audit),
        ('Format-Neutral Strategy', fn_audit),
        ('Grounded Sketch', gs_audit),
        ('Case', case_audit)
    ]:
        operator_only = sum(1 for r in audit_list if r['execution_status'] == 'operator_only')
        executable = sum(1 for r in audit_list if r['execution_status'] == 'success')
        correct = sum(1 for r in audit_list if r['program_correct'])

        print(f"\n{arm_name}:")
        print(f"  Total: {len(audit_list)}")
        print(f"  Operator-only: {operator_only}/{len(audit_list)} ({100.0*operator_only/len(audit_list):.1f}%)")
        print(f"  Executable: {executable}/{len(audit_list)} ({100.0*executable/len(audit_list):.1f}%)")
        print(f"  Correct: {correct}/{len(audit_list)} ({100.0*correct/len(audit_list):.1f}%)")

    print("\nAudit saved to stage38_pilot_audit.json")

if __name__ == '__main__':
    main()
