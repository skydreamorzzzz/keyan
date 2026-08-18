#!/usr/bin/env python3
"""
Evaluate Fidelity Experiment

Use canonical evaluator V2 to evaluate all corruption levels.
"""

import json
import sys
import glob

sys.path.insert(0, '/home/tiantian/keyan/pilot/stage36_paired_abstraction')
from canonical_evaluator_v2 import evaluate_response_v2

BASE_PATH = '/home/tiantian/keyan/pilot/stage41_abstraction_fidelity'
SOURCE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['pilot', 'full'], required=True)
    args = parser.parse_args()

    print("="*80)
    print("EVALUATE FIDELITY EXPERIMENT")
    print("="*80)
    print(f"Phase: {args.phase}")
    print()

    # Load targets
    with open(f'{SOURCE_PATH}/expanded_sample_queries.json') as f:
        targets = json.load(f)
    target_map = {t['id']: t for t in targets}

    # Find result files
    pattern = f'{BASE_PATH}/results_{args.phase}_*.json'
    result_files = sorted(glob.glob(pattern))

    print(f"Found {len(result_files)} result files")
    print()

    all_evaluations = {}
    all_metrics = {}

    for result_file in result_files:
        # Extract level from filename
        level = result_file.split('_')[-1].replace('.json', '').replace('pct', '%')

        print(f"Evaluating {level}...")

        with open(result_file) as f:
            responses = json.load(f)

        # Evaluate each response
        evaluations = []
        for resp in responses:
            target = target_map[resp['target_id']]
            eval_record = evaluate_response_v2(resp, target)
            evaluations.append(eval_record)

        # Compute metrics
        total = len(evaluations)
        correct = sum(1 for e in evaluations if e['program_correct'])

        error_categories = {}
        for e in evaluations:
            if not e['program_correct']:
                cat = e.get('error_category', 'unknown')
                error_categories[cat] = error_categories.get(cat, 0) + 1

        metrics = {
            'total': total,
            'correct': correct,
            'accuracy': correct / total if total > 0 else 0.0,
            'error_categories': error_categories
        }

        all_evaluations[level] = evaluations
        all_metrics[level] = metrics

        print(f"  Accuracy: {correct}/{total} ({100*metrics['accuracy']:.1f}%)")
        print(f"  Errors: {error_categories}")
        print()

    # Save
    output = {
        'phase': args.phase,
        'evaluations': all_evaluations,
        'metrics': all_metrics,
        'evaluator': 'canonical_evaluator_v2'
    }

    output_file = f'{BASE_PATH}/evaluations_{args.phase}.json'
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Saved: {output_file}")
    print()

    # Quick summary
    print("="*80)
    print("ACCURACY BY CORRUPTION LEVEL")
    print("="*80)

    for level in ['0%', '10%', '25%', '50%']:
        if level in all_metrics:
            metrics = all_metrics[level]
            print(f"{level:>5}: {metrics['accuracy']:.1%} ({metrics['correct']}/{metrics['total']})")

    print()

    # Check for dose-response
    if all(level in all_metrics for level in ['0%', '10%', '25%', '50%']):
        accs = [all_metrics[level]['accuracy'] for level in ['0%', '10%', '25%', '50%']]

        print("Dose-response check:")
        monotonic_decrease = all(accs[i] >= accs[i+1] for i in range(len(accs)-1))
        print(f"  Monotonic decrease: {monotonic_decrease}")
        print(f"  0% → 50% drop: {100*(accs[0] - accs[-1]):.1f}pp")
        print()

    print("Next: Statistical analysis")
    print(f"  python3 analyze_fidelity_results.py --phase {args.phase}")


if __name__ == '__main__':
    main()
