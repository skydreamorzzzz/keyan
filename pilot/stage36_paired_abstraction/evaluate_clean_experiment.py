#!/usr/bin/env python3
"""
Evaluate Clean Experiment Results

Use canonical_evaluator_v2 to evaluate both arms.
"""

import json
import sys

sys.path.insert(0, '/home/tiantian/keyan/pilot/stage36_paired_abstraction')
from canonical_evaluator_v2 import evaluate_arm_v2


BASE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'


def main():
    """Evaluate clean experiment results."""

    print("="*80)
    print("CLEAN EXPERIMENT EVALUATION")
    print("="*80)
    print()

    # Load targets
    with open(f'{BASE_PATH}/expanded_sample_queries.json') as f:
        targets = json.load(f)
    target_map = {t['id']: t for t in targets}

    print(f"Loaded {len(targets)} targets")
    print()

    # Evaluate both arms
    arms = {
        'Clean-FN': f'{BASE_PATH}/results_clean_fn.json',
        'Clean-FN+Sketch': f'{BASE_PATH}/results_clean_fn_sketch.json'
    }

    all_evaluations = {}
    all_metrics = {}

    for arm_name, filepath in arms.items():
        print(f"Evaluating {arm_name}...")

        with open(filepath) as f:
            responses = json.load(f)

        evaluations, metrics = evaluate_arm_v2(arm_name, responses, target_map)
        all_evaluations[arm_name] = evaluations
        all_metrics[arm_name] = metrics

        print(f"  Accuracy: {metrics['correct']}/{metrics['total']} ({100*metrics['accuracy']:.1f}%)")
        print(f"  Errors: {metrics['error_categories']}")
        print()

    # Save results
    output = {
        'evaluations': all_evaluations,
        'metrics': all_metrics,
        'evaluator': 'canonical_evaluator_v2',
        'note': 'Clean experiment: Clean-FN vs Clean-FN+Sketch'
    }

    output_file = f'{BASE_PATH}/clean_experiment_evaluations.json'
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print("="*80)
    print(f"Saved: {output_file}")
    print("="*80)
    print()

    # Quick comparison
    acc_fn = all_metrics['Clean-FN']['accuracy']
    acc_fns = all_metrics['Clean-FN+Sketch']['accuracy']
    diff = acc_fns - acc_fn

    print("QUICK COMPARISON:")
    print(f"  Clean-FN:        {100*acc_fn:.1f}%")
    print(f"  Clean-FN+Sketch: {100*acc_fns:.1f}%")
    print(f"  Difference:      {100*diff:+.1f}pp")
    print()
    print("Next: Statistical analysis (McNemar + Bootstrap CI)")
    print("  python3 clean_statistical_analysis.py")


if __name__ == '__main__':
    main()
