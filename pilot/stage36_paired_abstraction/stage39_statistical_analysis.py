#!/usr/bin/env python3
"""
Stage 39: Statistical Analysis
"""

import json
import numpy as np
from scipy.stats import binomtest
from typing import Dict, List, Tuple

BASE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'


def load_evaluations():
    """Load evaluation results."""
    with open(f'{BASE_PATH}/stage39_full224_evaluations.json') as f:
        data = json.load(f)
    return data['evaluations'], data['metrics']


def mcnemar_test(eval_a: List[Dict], eval_b: List[Dict]) -> Tuple[float, int, int]:
    """
    McNemar test for paired binary outcomes.
    Returns: (p_value, a_correct_b_wrong, a_wrong_b_correct)
    """

    # Build paired outcome matrix
    assert len(eval_a) == len(eval_b)

    # Match by target_id
    outcomes_a = {e['target_id']: e['program_correct'] for e in eval_a}
    outcomes_b = {e['target_id']: e['program_correct'] for e in eval_b}

    a_correct_b_wrong = 0
    a_wrong_b_correct = 0

    for tid in outcomes_a.keys():
        if outcomes_a[tid] and not outcomes_b[tid]:
            a_correct_b_wrong += 1
        elif not outcomes_a[tid] and outcomes_b[tid]:
            a_wrong_b_correct += 1

    # McNemar test: H0: marginal probabilities equal
    # Test statistic: (b - c)^2 / (b + c), approximately chi-squared(1)
    # Or use exact binomial test

    n_discordant = a_correct_b_wrong + a_wrong_b_correct

    if n_discordant == 0:
        return 1.0, 0, 0

    # Exact binomial test: P(X >= max(b,c) | n, p=0.5)
    p_value = binomtest(max(a_correct_b_wrong, a_wrong_b_correct), n_discordant, 0.5, alternative='two-sided').pvalue

    return p_value, a_correct_b_wrong, a_wrong_b_correct


def paired_bootstrap_ci(eval_a: List[Dict], eval_b: List[Dict],
                        n_bootstrap: int = 10000, alpha: float = 0.05) -> Tuple[float, float, float]:
    """
    Paired bootstrap CI for accuracy difference.
    Returns: (mean_diff, ci_lower, ci_upper)
    """

    # Match by target_id
    outcomes_a = {e['target_id']: int(e['program_correct']) for e in eval_a}
    outcomes_b = {e['target_id']: int(e['program_correct']) for e in eval_b}

    target_ids = list(outcomes_a.keys())
    n = len(target_ids)

    bootstrap_diffs = []

    for _ in range(n_bootstrap):
        # Resample target IDs with replacement
        sample_ids = np.random.choice(target_ids, size=n, replace=True)

        acc_a = np.mean([outcomes_a[tid] for tid in sample_ids])
        acc_b = np.mean([outcomes_b[tid] for tid in sample_ids])

        bootstrap_diffs.append(acc_a - acc_b)

    # Original difference
    acc_a_orig = np.mean(list(outcomes_a.values()))
    acc_b_orig = np.mean(list(outcomes_b.values()))
    mean_diff = acc_a_orig - acc_b_orig

    # CI from percentiles
    ci_lower = np.percentile(bootstrap_diffs, 100 * alpha / 2)
    ci_upper = np.percentile(bootstrap_diffs, 100 * (1 - alpha / 2))

    return mean_diff, ci_lower, ci_upper


def disagreement_analysis(eval_a: List[Dict], eval_b: List[Dict]) -> Dict:
    """
    Analyze disagreement patterns.
    Returns: rescue/harm counts, unique rescues
    """

    outcomes_a = {e['target_id']: e['program_correct'] for e in eval_a}
    outcomes_b = {e['target_id']: e['program_correct'] for e in eval_b}

    a_rescue = sum(1 for tid in outcomes_a if outcomes_a[tid] and not outcomes_b[tid])
    b_rescue = sum(1 for tid in outcomes_a if not outcomes_a[tid] and outcomes_b[tid])
    both_correct = sum(1 for tid in outcomes_a if outcomes_a[tid] and outcomes_b[tid])
    both_wrong = sum(1 for tid in outcomes_a if not outcomes_a[tid] and not outcomes_b[tid])

    return {
        'a_rescue_b_fail': a_rescue,
        'b_rescue_a_fail': b_rescue,
        'both_correct': both_correct,
        'both_wrong': both_wrong
    }


def unique_rescue_analysis(all_evaluations: Dict[str, List[Dict]]) -> Dict:
    """
    Find queries where only one arm succeeds.
    """

    arm_names = list(all_evaluations.keys())

    # Build outcome matrix: target_id -> {arm: correct}
    all_target_ids = set(e['target_id'] for e in all_evaluations[arm_names[0]])

    outcome_matrix = {}
    for tid in all_target_ids:
        outcome_matrix[tid] = {}
        for arm in arm_names:
            outcome_matrix[tid][arm] = next(
                (e['program_correct'] for e in all_evaluations[arm] if e['target_id'] == tid),
                False
            )

    # Find unique rescues per arm
    unique_rescues = {}
    for arm in arm_names:
        unique_rescues[arm] = []
        for tid, outcomes in outcome_matrix.items():
            if outcomes[arm] and not any(outcomes[other] for other in arm_names if other != arm):
                unique_rescues[arm].append(tid)

    return unique_rescues


def main():
    """Run statistical analysis."""

    print("="*80)
    print("STAGE 39: STATISTICAL ANALYSIS")
    print("="*80)

    evaluations, metrics = load_evaluations()

    arms = list(evaluations.keys())

    # Primary comparisons
    comparisons = [
        ('Grounded Sketch', 'Case'),
        ('Grounded Sketch', 'Format-Neutral+Binding'),
        ('Format-Neutral+Binding', 'Format-Neutral'),
        ('Format-Neutral', 'Case')
    ]

    results = {}

    for arm_a, arm_b in comparisons:
        print(f"\n{'-'*60}")
        print(f"Comparing: {arm_a} vs {arm_b}")

        eval_a = evaluations[arm_a]
        eval_b = evaluations[arm_b]

        # McNemar test
        p_value, a_rescue, b_rescue = mcnemar_test(eval_a, eval_b)

        # Bootstrap CI
        mean_diff, ci_lower, ci_upper = paired_bootstrap_ci(eval_a, eval_b)

        # Disagreement
        disagree = disagreement_analysis(eval_a, eval_b)

        print(f"  Accuracy: {arm_a} {100*metrics[arm_a]['accuracy']:.1f}% vs {arm_b} {100*metrics[arm_b]['accuracy']:.1f}%")
        print(f"  Difference: {100*mean_diff:+.1f}pp (95% CI: [{100*ci_lower:.1f}, {100*ci_upper:.1f}])")
        print(f"  McNemar p-value: {p_value:.4f}")
        print(f"  Rescue: {arm_a}={a_rescue}, {arm_b}={b_rescue}")

        results[f"{arm_a}_vs_{arm_b}"] = {
            'accuracy_diff': mean_diff,
            'ci_95': [ci_lower, ci_upper],
            'mcnemar_p': p_value,
            'rescue_counts': disagree
        }

    # Unique rescues
    print(f"\n{'-'*60}")
    print("Unique rescues (only one arm correct):")
    unique = unique_rescue_analysis(evaluations)
    for arm, tids in unique.items():
        print(f"  {arm}: {len(tids)} unique rescues")
        results[f"{arm}_unique_rescues"] = tids

    # Save results
    with open(f'{BASE_PATH}/stage39_statistical_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*80}")
    print("Statistical analysis saved to stage39_statistical_results.json")


if __name__ == '__main__':
    main()
