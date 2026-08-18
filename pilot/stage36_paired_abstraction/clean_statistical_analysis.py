#!/usr/bin/env python3
"""
Clean Experiment Statistical Analysis

McNemar test + Bootstrap CI for Clean-FN vs Clean-FN+Sketch.
"""

import json
import numpy as np
from scipy.stats import binomtest

BASE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'


def mcnemar_test_paired(eval_a, eval_b):
    """McNemar test for paired binary outcomes."""
    outcomes_a = {e['target_id']: e['program_correct'] for e in eval_a}
    outcomes_b = {e['target_id']: e['program_correct'] for e in eval_b}

    a_correct_b_wrong = 0
    a_wrong_b_correct = 0

    for tid in outcomes_a.keys():
        if outcomes_a[tid] and not outcomes_b[tid]:
            a_correct_b_wrong += 1
        elif not outcomes_a[tid] and outcomes_b[tid]:
            a_wrong_b_correct += 1

    n_discordant = a_correct_b_wrong + a_wrong_b_correct

    if n_discordant == 0:
        return 1.0, 0, 0

    p_value = binomtest(
        max(a_correct_b_wrong, a_wrong_b_correct),
        n_discordant,
        0.5,
        alternative='two-sided'
    ).pvalue

    return p_value, a_correct_b_wrong, a_wrong_b_correct


def bootstrap_ci_paired(eval_a, eval_b, n_bootstrap=10000, alpha=0.05):
    """Paired bootstrap CI for accuracy difference."""
    outcomes_a = {e['target_id']: int(e['program_correct']) for e in eval_a}
    outcomes_b = {e['target_id']: int(e['program_correct']) for e in eval_b}

    target_ids = list(outcomes_a.keys())
    n = len(target_ids)

    bootstrap_diffs = []
    np.random.seed(42)

    for _ in range(n_bootstrap):
        sample_ids = np.random.choice(target_ids, size=n, replace=True)
        acc_a = np.mean([outcomes_a[tid] for tid in sample_ids])
        acc_b = np.mean([outcomes_b[tid] for tid in sample_ids])
        bootstrap_diffs.append(acc_b - acc_a)

    acc_a_orig = np.mean(list(outcomes_a.values()))
    acc_b_orig = np.mean(list(outcomes_b.values()))
    mean_diff = acc_b_orig - acc_a_orig

    ci_lower = np.percentile(bootstrap_diffs, 100 * alpha / 2)
    ci_upper = np.percentile(bootstrap_diffs, 100 * (1 - alpha / 2))

    return mean_diff, ci_lower, ci_upper


def main():
    """Run statistical analysis."""

    print("="*80)
    print("CLEAN EXPERIMENT STATISTICAL ANALYSIS")
    print("="*80)
    print()

    # Load evaluations
    with open(f'{BASE_PATH}/clean_experiment_evaluations.json') as f:
        data = json.load(f)

    evaluations = data['evaluations']
    metrics = data['metrics']

    eval_fn = evaluations['Clean-FN']
    eval_fns = evaluations['Clean-FN+Sketch']

    # McNemar test
    print("McNemar Test: Clean-FN+Sketch vs Clean-FN")
    print("-"*80)

    p_value, fns_rescue, fn_rescue = mcnemar_test_paired(eval_fns, eval_fn)

    acc_fn = metrics['Clean-FN']['accuracy']
    acc_fns = metrics['Clean-FN+Sketch']['accuracy']
    diff = acc_fns - acc_fn

    print(f"Accuracy:")
    print(f"  Clean-FN:        {acc_fn:.1%} ({metrics['Clean-FN']['correct']}/{metrics['Clean-FN']['total']})")
    print(f"  Clean-FN+Sketch: {acc_fns:.1%} ({metrics['Clean-FN+Sketch']['correct']}/{metrics['Clean-FN+Sketch']['total']})")
    print(f"  Difference:      {100*diff:+.1f}pp")
    print()

    print(f"McNemar Test:")
    print(f"  p-value: {p_value:.4f}")
    print(f"  Significant (α=0.05): {'YES' if p_value < 0.05 else 'NO'}")
    print()

    print(f"Disagreement:")
    print(f"  Clean-FN+Sketch rescues: {fns_rescue}")
    print(f"  Clean-FN rescues: {fn_rescue}")
    print(f"  Ratio: {fns_rescue}:{fn_rescue}")
    print()

    # Bootstrap CI
    print("Bootstrap CI (10,000 iterations)")
    print("-"*80)

    mean_diff, ci_lower, ci_upper = bootstrap_ci_paired(eval_fn, eval_fns)

    print(f"Mean difference: {100*mean_diff:+.1f}pp")
    print(f"95% CI: [{100*ci_lower:.1f}, {100*ci_upper:.1f}]")
    print()

    # Interpretation
    print("="*80)
    print("INTERPRETATION")
    print("="*80)

    if p_value < 0.05:
        print("✓ Program sketch has SIGNIFICANT effect (p < 0.05)")
    else:
        print("✗ Program sketch does NOT have significant effect (p ≥ 0.05)")

    if ci_lower > 0:
        print("✓ Effect is reliably positive (95% CI excludes 0)")
    elif ci_upper < 0:
        print("✗ Effect is reliably negative (95% CI excludes 0)")
    else:
        print("⚠️  Effect is uncertain (95% CI includes 0)")

    print()
    print(f"Effect size: +{100*diff:.1f}pp ({100*diff/acc_fn:.1f}% relative improvement)")
    print()

    # Save results
    output = {
        'comparison': 'Clean-FN+Sketch vs Clean-FN',
        'accuracy_fn': float(acc_fn),
        'accuracy_fns': float(acc_fns),
        'difference_pp': float(diff * 100),
        'ci_95_lower_pp': float(ci_lower * 100),
        'ci_95_upper_pp': float(ci_upper * 100),
        'mcnemar_p': float(p_value),
        'significant_at_05': bool(p_value < 0.05),
        'fns_rescue': int(fns_rescue),
        'fn_rescue': int(fn_rescue),
        'rescue_ratio': f'{fns_rescue}:{fn_rescue}',
        'note': 'Clean experiment with cleaned strategies (5.1% contamination)'
    }

    output_file = f'{BASE_PATH}/clean_statistical_analysis.json'
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Saved: {output_file}")
    print("="*80)


if __name__ == '__main__':
    main()
