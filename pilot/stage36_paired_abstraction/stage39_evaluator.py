#!/usr/bin/env python3
"""
Stage 39: Program-Level Evaluator
"""

import json
import re
import sys

sys.path.insert(0, '/home/tiantian/keyan/pilot')
from executor import parse_program_re, parse_linear_steps, exec_steps

BASE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'


def evaluate_response(response_record, target_map):
    """Evaluate single response with program-level execution."""

    target_id = response_record['target_id']
    target = target_map[target_id]
    gold_answer = target['qa']['exe_ans']

    response_text = response_record['response']

    # Extract program
    program_match = re.search(
        r'PROGRAM:\s*(.+?)(?=\nANSWER:|$)',
        response_text,
        re.DOTALL
    )

    if not program_match:
        return {
            'target_id': target_id,
            'arm': response_record.get('arm', 'unknown'),
            'gold_answer': gold_answer,
            'raw_program': None,
            'execution_status': 'no_program',
            'execution_result': None,
            'program_correct': False
        }

    raw_program = program_match.group(1).strip()

    # Check operator-only pattern
    if re.match(r'^[a-z_]+(?:\s*,\s*[a-z_]+)*\s*$', raw_program):
        return {
            'target_id': target_id,
            'arm': response_record.get('arm', 'unknown'),
            'gold_answer': gold_answer,
            'raw_program': raw_program,
            'execution_status': 'operator_only',
            'execution_result': None,
            'program_correct': False
        }

    # Normalize and parse
    normalized = raw_program.replace('\n', ', ')

    try:
        # Detect format: linear (has top-level commas) or nested (single expression)
        # This matches Stage 37's execute_program_with_table logic
        depth = 0
        has_top_level_comma = False
        for c in normalized:
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            elif c == ',' and depth == 0:
                has_top_level_comma = True
                break

        # Parse program to linear steps
        if has_top_level_comma:
            # Linear format: use parse_linear_steps (handles multi-step programs)
            steps = parse_linear_steps(normalized)
        else:
            # Nested format: use parse_program_re (handles single nested expression)
            steps = parse_program_re(normalized)

        if not steps:
            return {
                'target_id': target_id,
                'arm': response_record.get('arm', 'unknown'),
                'gold_answer': gold_answer,
                'raw_program': raw_program,
                'execution_status': 'parse_fail',
                'execution_result': None,
                'program_correct': False
            }

        # Execute
        try:
            success, result = exec_steps(steps, target)

            if not success:
                return {
                    'target_id': target_id,
                    'arm': response_record.get('arm', 'unknown'),
                    'gold_answer': gold_answer,
                    'raw_program': raw_program,
                    'execution_status': 'exec_fail',
                    'execution_result': None,
                    'program_correct': False
                }

            # Compare with gold
            correct = abs(float(result) - float(gold_answer)) < 1e-4

            return {
                'target_id': target_id,
                'arm': response_record.get('arm', 'unknown'),
                'gold_answer': gold_answer,
                'raw_program': raw_program,
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
            'execution_status': 'parse_fail',
            'execution_result': None,
            'program_correct': False
        }


def evaluate_arm(arm_name, results_file, target_map):
    """Evaluate all responses for one arm."""

    with open(results_file) as f:
        responses = json.load(f)

    print(f"Evaluating {arm_name}: {len(responses)} responses")

    evaluations = []
    for resp in responses:
        eval_record = evaluate_response(resp, target_map)
        evaluations.append(eval_record)

    return evaluations


def compute_metrics(evaluations):
    """Compute summary metrics."""

    total = len(evaluations)
    operator_only = sum(1 for e in evaluations if e['execution_status'] == 'operator_only')
    parse_fail = sum(1 for e in evaluations if e['execution_status'] == 'parse_fail')
    exec_fail = sum(1 for e in evaluations if e['execution_status'] == 'exec_fail')
    executable = sum(1 for e in evaluations if e['execution_status'] == 'success')
    correct = sum(1 for e in evaluations if e['program_correct'])

    return {
        'total': total,
        'operator_only': operator_only,
        'parse_fail': parse_fail,
        'exec_fail': exec_fail,
        'executable': executable,
        'correct': correct,
        'operator_only_rate': operator_only / total,
        'executable_rate': executable / total,
        'accuracy': correct / total
    }


def main():
    """Run full evaluation on all arms."""

    print("="*80)
    print("STAGE 39: PROGRAM-LEVEL EVALUATION")
    print("="*80)

    # Load targets
    with open(f'{BASE_PATH}/expanded_sample_queries.json') as f:
        targets = json.load(f)
    target_map = {t['id']: t for t in targets}

    print(f"\nLoaded {len(targets)} targets")

    # Evaluate all arms
    arms = {
        'Case': f'{BASE_PATH}/results_case_expanded.json',
        'Format-Neutral': f'{BASE_PATH}/results_format_neutral_full224.json',
        'Format-Neutral+Binding': f'{BASE_PATH}/results_format_neutral_binding_full224.json',
        'Grounded Sketch': f'{BASE_PATH}/results_grounded_sketch_full224.json'
    }

    all_evaluations = {}
    all_metrics = {}

    for arm_name, results_file in arms.items():
        print(f"\n{'-'*60}")
        evals = evaluate_arm(arm_name, results_file, target_map)
        metrics = compute_metrics(evals)

        all_evaluations[arm_name] = evals
        all_metrics[arm_name] = metrics

        print(f"{arm_name}:")
        print(f"  Accuracy: {metrics['correct']}/{metrics['total']} ({100*metrics['accuracy']:.1f}%)")
        print(f"  Executable: {metrics['executable']}/{metrics['total']} ({100*metrics['executable_rate']:.1f}%)")
        print(f"  Operator-only: {metrics['operator_only']}/{metrics['total']} ({100*metrics['operator_only_rate']:.1f}%)")

    # Save evaluations
    output = {
        'evaluations': all_evaluations,
        'metrics': all_metrics
    }

    with open(f'{BASE_PATH}/stage39_full224_evaluations.json', 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n{'='*80}")
    print("Evaluation saved to stage39_full224_evaluations.json")
    print(f"{'='*80}")
    print("\nNext: Run stage39_statistical_analysis.py for significance tests")


if __name__ == '__main__':
    main()
