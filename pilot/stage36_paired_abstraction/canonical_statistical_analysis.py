#!/usr/bin/env python3
"""
Canonical Statistical Analysis

使用 canonical evaluator 的结果重新做完整统计分析:
1. McNemar test for paired comparisons
2. Bootstrap CI for effect sizes
3. Disagreement pattern analysis
4. Comprehensive report
"""

import json
import numpy as np
from scipy.stats import binomtest
from typing import Dict, List, Tuple


BASE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'


def load_canonical_evaluations():
    """Load canonical evaluation results."""
    with open(f'{BASE_PATH}/canonical_evaluations.json') as f:
        data = json.load(f)
    return data['evaluations'], data['metrics']


def mcnemar_test_paired(eval_a: List[Dict], eval_b: List[Dict]) -> Tuple[float, int, int]:
    """
    McNemar test for paired binary outcomes.

    Returns:
        (p_value, a_rescue_count, b_rescue_count)
    """
    # Build outcome dicts
    outcomes_a = {e['target_id']: e['program_correct'] for e in eval_a}
    outcomes_b = {e['target_id']: e['program_correct'] for e in eval_b}

    # Count discordant pairs
    a_correct_b_wrong = 0
    a_wrong_b_correct = 0

    for tid in outcomes_a.keys():
        if outcomes_a[tid] and not outcomes_b[tid]:
            a_correct_b_wrong += 1
        elif not outcomes_a[tid] and outcomes_b[tid]:
            a_wrong_b_correct += 1

    # McNemar exact binomial test
    n_discordant = a_correct_b_wrong + a_wrong_b_correct

    if n_discordant == 0:
        return 1.0, 0, 0

    # Two-sided test
    p_value = binomtest(
        max(a_correct_b_wrong, a_wrong_b_correct),
        n_discordant,
        0.5,
        alternative='two-sided'
    ).pvalue

    return p_value, a_correct_b_wrong, a_wrong_b_correct


def bootstrap_ci_paired(
    eval_a: List[Dict],
    eval_b: List[Dict],
    n_bootstrap: int = 10000,
    alpha: float = 0.05
) -> Tuple[float, float, float]:
    """
    Paired bootstrap CI for accuracy difference.

    Returns:
        (mean_diff, ci_lower, ci_upper)
    """
    outcomes_a = {e['target_id']: int(e['program_correct']) for e in eval_a}
    outcomes_b = {e['target_id']: int(e['program_correct']) for e in eval_b}

    target_ids = list(outcomes_a.keys())
    n = len(target_ids)

    # Bootstrap resampling
    bootstrap_diffs = []
    np.random.seed(42)

    for _ in range(n_bootstrap):
        sample_ids = np.random.choice(target_ids, size=n, replace=True)
        acc_a = np.mean([outcomes_a[tid] for tid in sample_ids])
        acc_b = np.mean([outcomes_b[tid] for tid in sample_ids])
        bootstrap_diffs.append(acc_a - acc_b)

    # Observed difference
    acc_a_orig = np.mean(list(outcomes_a.values()))
    acc_b_orig = np.mean(list(outcomes_b.values()))
    mean_diff = acc_a_orig - acc_b_orig

    # Percentile CI
    ci_lower = np.percentile(bootstrap_diffs, 100 * alpha / 2)
    ci_upper = np.percentile(bootstrap_diffs, 100 * (1 - alpha / 2))

    return mean_diff, ci_lower, ci_upper


def analyze_comparison(
    name_a: str,
    name_b: str,
    eval_a: List[Dict],
    eval_b: List[Dict],
    metrics_a: Dict,
    metrics_b: Dict
) -> Dict:
    """Comprehensive analysis of one comparison."""

    # McNemar test
    p_value, a_rescue, b_rescue = mcnemar_test_paired(eval_a, eval_b)

    # Bootstrap CI
    mean_diff, ci_lower, ci_upper = bootstrap_ci_paired(eval_a, eval_b)

    # Accuracy
    acc_a = metrics_a['accuracy']
    acc_b = metrics_b['accuracy']

    # Determine significance at α=0.05
    significant = p_value < 0.05

    return {
        'comparison': f'{name_a} vs {name_b}',
        'accuracy_a': float(acc_a),
        'accuracy_b': float(acc_b),
        'difference_pp': float(mean_diff * 100),
        'ci_95_lower_pp': float(ci_lower * 100),
        'ci_95_upper_pp': float(ci_upper * 100),
        'mcnemar_p': float(p_value),
        'significant_at_05': bool(significant),
        'a_rescue': int(a_rescue),
        'b_rescue': int(b_rescue),
        'rescue_ratio': f'{a_rescue}:{b_rescue}'
    }


def main():
    """Run comprehensive statistical analysis."""

    print("="*80)
    print("CANONICAL STATISTICAL ANALYSIS")
    print("="*80)
    print()

    # Load data
    evaluations, metrics = load_canonical_evaluations()

    # Define comparisons
    comparisons = [
        # Primary: GS vs baselines
        ('Grounded-Sketch_Stage39', 'Case_Stage37'),
        ('Grounded-Sketch_Stage39', 'Format-Neutral+Binding_Stage39'),

        # Secondary: baselines vs each other
        ('Case_Stage37', 'Format-Neutral_Stage39'),
        ('Format-Neutral+Binding_Stage39', 'Format-Neutral_Stage39'),

        # Additional: all vs all
        ('Grounded-Sketch_Stage39', 'Format-Neutral_Stage39'),
    ]

    results = []

    for arm_a, arm_b in comparisons:
        # Get display names
        name_a = arm_a.replace('_Stage37', '').replace('_Stage39', '').replace('-', ' ')
        name_b = arm_b.replace('_Stage37', '').replace('_Stage39', '').replace('-', ' ')

        print(f"\n{'='*80}")
        print(f"COMPARING: {name_a} vs {name_b}")
        print(f"{'='*80}")

        result = analyze_comparison(
            name_a, name_b,
            evaluations[arm_a], evaluations[arm_b],
            metrics[arm_a], metrics[arm_b]
        )

        results.append(result)

        # Print results
        print(f"\nAccuracy:")
        print(f"  {name_a}: {result['accuracy_a']:.1%}")
        print(f"  {name_b}: {result['accuracy_b']:.1%}")
        print(f"  Difference: {result['difference_pp']:+.1f}pp")
        print(f"  95% CI: [{result['ci_95_lower_pp']:.1f}, {result['ci_95_upper_pp']:.1f}]")
        print()
        print(f"McNemar Test:")
        print(f"  p-value: {result['mcnemar_p']:.4f}")
        print(f"  Significant (α=0.05): {'YES' if result['significant_at_05'] else 'NO'}")
        print()
        print(f"Disagreement:")
        print(f"  {name_a} rescues: {result['a_rescue']}")
        print(f"  {name_b} rescues: {result['b_rescue']}")
        print(f"  Ratio: {result['rescue_ratio']}")

    # Save results
    output = {
        'comparisons': results,
        'note': 'Based on canonical evaluator with case-insensitive PROGRAM extraction'
    }

    with open(f'{BASE_PATH}/canonical_statistical_analysis.json', 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print()

    # Summary table
    print(f"{'Comparison':<50} {'Δ':<10} {'p-value':<12} {'Significant'}")
    print("-"*80)

    for r in results:
        sig_marker = "✓" if r['significant_at_05'] else "✗"
        print(f"{r['comparison']:<50} {r['difference_pp']:>+6.1f}pp   {r['mcnemar_p']:>8.4f}    {sig_marker}")

    print()
    print(f"Saved to: canonical_statistical_analysis.json")
    print("="*80)


if __name__ == '__main__':
    main()
