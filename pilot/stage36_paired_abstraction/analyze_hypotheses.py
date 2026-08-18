"""H1-H5 信号分析：从实验结果中提取假设相关的定性证据。

不设统计显著性阈值，报告观测到的模式和方向。
"""
import json
import os
import numpy as np
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def load_results():
    """Load experiment results."""
    base_path = os.path.join(ROOT, "pilot/stage36_paired_abstraction")

    with open(os.path.join(base_path, "experiment_results.json")) as f:
        results = json.load(f)

    return results

def analyze_h1_concrete_semantic_dependence(results):
    """H1: Concrete Case 表征更依赖语义相似度。

    Signal: Case arm 的 EM 与 semantic similarity 相关性 > Strategy arm
    """
    print("=" * 80)
    print("H1: Concrete Case 依赖语义相似度")
    print("=" * 80)
    print()

    correlations = results.get("correlations", [])

    # Extract Case vs Strategy correlations with semantic similarity
    case_data = [c for c in correlations if c["arm"] == "Case"]
    strategy_data = [c for c in correlations if c["arm"] == "Strategy"]

    if not case_data or not strategy_data:
        print("⚠ Insufficient data for H1 analysis")
        return

    # Compute correlation for each arm
    from scipy.stats import spearmanr

    case_ems = [c["exact_match"] for c in case_data]
    case_sems = [c["avg_semantic_similarity"] for c in case_data]

    strategy_ems = [c["exact_match"] for c in strategy_data]
    strategy_sems = [c["avg_semantic_similarity"] for c in strategy_data]

    # Check variance
    if np.var(case_ems) > 0:
        case_corr, case_p = spearmanr(case_ems, case_sems)
    else:
        case_corr, case_p = 0.0, 1.0

    if np.var(strategy_ems) > 0:
        strategy_corr, strategy_p = spearmanr(strategy_ems, strategy_sems)
    else:
        strategy_corr, strategy_p = 0.0, 1.0

    print(f"Case arm EM vs Semantic Similarity:     ρ = {case_corr:.3f} (p={case_p:.3f})")
    print(f"Strategy arm EM vs Semantic Similarity: ρ = {strategy_corr:.3f} (p={strategy_p:.3f})")
    print()

    # Interpret
    if case_corr > strategy_corr + 0.1:
        print("→ Signal SUPPORTS H1: Case shows stronger semantic dependence")
    elif strategy_corr > case_corr + 0.1:
        print("→ Signal CONTRADICTS H1: Strategy shows stronger semantic dependence")
    else:
        print("→ Signal WEAK: Similar semantic dependence across arms")

    print()

def analyze_h2_strategy_reasoning_alignment(results):
    """H2: Strategy(E) 在语义相似度低但推理对齐高时更有效。

    Signal: Strategy correct / Case wrong 的 queries 有更高的 reasoning alignment
    """
    print("=" * 80)
    print("H2: Strategy 在低语义/高推理对齐时有效")
    print("=" * 80)
    print()

    query_results = results.get("query_results", {})
    correlations = results.get("correlations", [])

    # Find queries where Strategy correct but Case wrong
    strategy_wins = []
    case_wins = []
    both_correct = []
    both_wrong = []

    for target_id, arms in query_results.items():
        case_em = arms.get("Case", False)
        strategy_em = arms.get("Strategy", False)

        # Get diagnostics for this query
        query_corr = [c for c in correlations if c["target_id"] == target_id and c["arm"] == "Strategy"]
        if not query_corr:
            continue

        diag = query_corr[0]

        if strategy_em and not case_em:
            strategy_wins.append(diag)
        elif case_em and not strategy_em:
            case_wins.append(diag)
        elif case_em and strategy_em:
            both_correct.append(diag)
        else:
            both_wrong.append(diag)

    print(f"Strategy correct / Case wrong: {len(strategy_wins)} queries")
    print(f"Case correct / Strategy wrong: {len(case_wins)} queries")
    print(f"Both correct: {len(both_correct)} queries")
    print(f"Both wrong: {len(both_wrong)} queries")
    print()

    if strategy_wins and case_wins:
        # Compare diagnostics
        strategy_win_semantic = np.mean([d["avg_semantic_similarity"] for d in strategy_wins])
        strategy_win_reasoning = np.mean([d["avg_operation_family_overlap"] for d in strategy_wins])

        case_win_semantic = np.mean([d["avg_semantic_similarity"] for d in case_wins])
        case_win_reasoning = np.mean([d["avg_operation_family_overlap"] for d in case_wins])

        print("Average diagnostics:")
        print(f"  Strategy wins: semantic={strategy_win_semantic:.3f}, reasoning={strategy_win_reasoning:.3f}")
        print(f"  Case wins:     semantic={case_win_semantic:.3f}, reasoning={case_win_reasoning:.3f}")
        print()

        # Check if Strategy wins have higher reasoning alignment
        if strategy_win_reasoning > case_win_reasoning and strategy_win_semantic < case_win_semantic:
            print("→ Signal SUPPORTS H2: Strategy wins show lower semantic but higher reasoning alignment")
        elif strategy_win_reasoning <= case_win_reasoning:
            print("→ Signal CONTRADICTS H2: Strategy wins do not show higher reasoning alignment")
        else:
            print("→ Signal MIXED: Pattern partially consistent with H2")
    else:
        print("⚠ Insufficient transition data for H2 analysis")

    print()

def analyze_h3_negative_interference(results):
    """H3: Strategy(E) 改变负面干扰模式。

    Signal: Case wrong / Strategy correct 的 queries 中，Case retrieval 的语义相似度分布
    """
    print("=" * 80)
    print("H3: Strategy 改变负面干扰")
    print("=" * 80)
    print()

    query_results = results.get("query_results", {})
    correlations = results.get("correlations", [])

    # Find queries where Case wrong
    case_wrong = []
    case_correct = []

    for target_id, arms in query_results.items():
        case_em = arms.get("Case", False)

        # Get diagnostics
        query_corr = [c for c in correlations if c["target_id"] == target_id and c["arm"] == "Case"]
        if not query_corr:
            continue

        diag = query_corr[0]

        if case_em:
            case_correct.append(diag)
        else:
            case_wrong.append(diag)

    if case_wrong and case_correct:
        wrong_semantic = [d["avg_semantic_similarity"] for d in case_wrong]
        correct_semantic = [d["avg_semantic_similarity"] for d in case_correct]

        print(f"Case wrong: n={len(case_wrong)}, semantic mean={np.mean(wrong_semantic):.3f}")
        print(f"Case correct: n={len(case_correct)}, semantic mean={np.mean(correct_semantic):.3f}")
        print()

        # Check if Case wrong has lower semantic similarity (suggesting irrelevant retrieval)
        if np.mean(wrong_semantic) < np.mean(correct_semantic) - 0.05:
            print("→ Signal SUPPORTS H3: Case failures have lower semantic similarity")
            print("   (Suggests concrete memory more vulnerable to irrelevant retrieval)")
        else:
            print("→ Signal WEAK: No clear semantic similarity difference in Case failures")

    print()

def analyze_h4_paired_complementarity(results):
    """H4: Paired Case+Strategy 互补 vs 冲突。

    Signal: Paired 优于 max(Case, Strategy) vs 劣于 max
    """
    print("=" * 80)
    print("H4: Paired 互补性")
    print("=" * 80)
    print()

    query_results = results.get("query_results", {})

    paired_beats_both = 0
    paired_worse_than_best = 0
    paired_same_as_best = 0

    for target_id, arms in query_results.items():
        case_em = arms.get("Case", False)
        strategy_em = arms.get("Strategy", False)
        paired_em = arms.get("Paired", False)

        best_single = case_em or strategy_em

        if paired_em and not best_single:
            paired_beats_both += 1
        elif not paired_em and best_single:
            paired_worse_than_best += 1
        elif paired_em and best_single:
            paired_same_as_best += 1

    total = len(query_results)

    print(f"Paired beats both single arms: {paired_beats_both} ({paired_beats_both/total*100:.1f}%)")
    print(f"Paired worse than best single: {paired_worse_than_best} ({paired_worse_than_best/total*100:.1f}%)")
    print(f"Paired same as best single: {paired_same_as_best} ({paired_same_as_best/total*100:.1f}%)")
    print()

    # Interpret
    if paired_beats_both > paired_worse_than_best:
        print("→ Signal SUPPORTS H4: Paired shows complementarity (more wins than losses)")
    elif paired_worse_than_best > paired_beats_both:
        print("→ Signal CONTRADICTS H4: Paired shows conflict/redundancy (more losses)")
    else:
        print("→ Signal NEUTRAL: Paired neither clearly complements nor conflicts")

    print()

def analyze_h5_reasoning_vs_semantic(results):
    """H5: 推理对齐比语义相似度更接近效用。

    Signal: EM 与 reasoning alignment 相关性 > semantic similarity
    """
    print("=" * 80)
    print("H5: 推理对齐更接近效用")
    print("=" * 80)
    print()

    correlations = results.get("correlations", [])

    # For each arm, compare semantic vs reasoning correlation with EM
    from scipy.stats import spearmanr

    for arm_name in ["None", "Case", "Strategy", "Paired"]:
        arm_data = [c for c in correlations if c["arm"] == arm_name]

        if len(arm_data) < 10:
            continue

        ems = [c["exact_match"] for c in arm_data]

        if np.var(ems) == 0:
            print(f"{arm_name} arm: All same EM, cannot compute correlation")
            continue

        semantics = [c["avg_semantic_similarity"] for c in arm_data]
        families = [c["avg_operation_family_overlap"] for c in arm_data]
        multisets = [c["avg_operation_multiset_similarity"] for c in arm_data]

        corr_sem, _ = spearmanr(ems, semantics)
        corr_fam, _ = spearmanr(ems, families)
        corr_multi, _ = spearmanr(ems, multisets)

        print(f"{arm_name} arm:")
        print(f"  EM vs Semantic Similarity:         ρ = {corr_sem:.3f}")
        print(f"  EM vs Operation Family Overlap:    ρ = {corr_fam:.3f}")
        print(f"  EM vs Operation Multiset Sim:      ρ = {corr_multi:.3f}")

        # Check if reasoning correlations higher
        max_reasoning = max(corr_fam, corr_multi)
        if max_reasoning > corr_sem + 0.1:
            print(f"  → Reasoning alignment shows stronger correlation with EM")
        elif corr_sem > max_reasoning + 0.1:
            print(f"  → Semantic similarity shows stronger correlation with EM")
        else:
            print(f"  → Similar correlation strength")

        print()

def main():
    print("=" * 80)
    print("STAGE 36: H1-H5 Signal Analysis")
    print("=" * 80)
    print()

    # Load results
    results = load_results()

    # Analyze each hypothesis
    analyze_h1_concrete_semantic_dependence(results)
    analyze_h2_strategy_reasoning_alignment(results)
    analyze_h3_negative_interference(results)
    analyze_h4_paired_complementarity(results)
    analyze_h5_reasoning_vs_semantic(results)

    print("=" * 80)
    print("INTERPRETATION GUIDELINES")
    print("=" * 80)
    print()
    print("1. 'Signal SUPPORTS' = observed pattern consistent with hypothesis")
    print("2. 'Signal CONTRADICTS' = observed pattern opposite to hypothesis")
    print("3. 'Signal WEAK/MIXED' = unclear or ambiguous pattern")
    print()
    print("⚠ 30-query pilot is FEASIBILITY study, not proof")
    print("⚠ No statistical significance thresholds applied")
    print("⚠ Report as exploratory evidence, not conclusive findings")

if __name__ == "__main__":
    main()
