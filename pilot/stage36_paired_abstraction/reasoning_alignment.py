"""Reasoning alignment diagnostic: Compare operation/structure alignment between
retrieved sources and target queries.

Oracle diagnostic using gold programs to measure:
1. Operation family overlap
2. Operation multiset similarity
3. Compositional structure alignment

This is NOT an inference-time retriever - it's post-hoc analysis to understand
what makes a retrieved source useful.
"""
import json
import os
import re
import sys
from collections import Counter
from typing import List, Dict, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

def extract_operations(program) -> List[str]:
    """Extract operation names from program steps.

    Handles multiple formats:
    - Single string: "divide(131, 5270)"
    - Comma-separated string: "subtract(17430.8, 16831.9), divide(#0, 16831.9)"
    - List of strings: ["subtract(17430.8, 16831.9)", "divide(#0, 16831.9)"]
    """
    ops = []

    # Handle string program (single or comma-separated)
    if isinstance(program, str):
        # Split by comma to handle multi-step programs
        steps = [s.strip() for s in program.split(',')]
        for step in steps:
            match = re.match(r'(\w+)\(', step)
            if match:
                ops.append(match.group(1))
        return ops

    # Handle list of steps
    if isinstance(program, list):
        for step in program:
            if isinstance(step, str):
                match = re.match(r'(\w+)\(', step)
                if match:
                    ops.append(match.group(1))

    return ops

def operation_family_overlap(source_ops: List[str], target_ops: List[str]) -> float:
    """Jaccard similarity of operation sets."""
    if not source_ops or not target_ops:
        return 0.0

    source_set = set(source_ops)
    target_set = set(target_ops)

    intersection = len(source_set & target_set)
    union = len(source_set | target_set)

    return intersection / union if union > 0 else 0.0

def operation_multiset_similarity(source_ops: List[str], target_ops: List[str]) -> float:
    """Cosine similarity of operation frequency vectors."""
    if not source_ops or not target_ops:
        return 0.0

    source_counts = Counter(source_ops)
    target_counts = Counter(target_ops)

    # Get all unique operations
    all_ops = set(source_ops + target_ops)

    # Build frequency vectors
    source_vec = [source_counts.get(op, 0) for op in all_ops]
    target_vec = [target_counts.get(op, 0) for op in all_ops]

    # Cosine similarity
    dot_product = sum(s * t for s, t in zip(source_vec, target_vec))
    source_norm = sum(s ** 2 for s in source_vec) ** 0.5
    target_norm = sum(t ** 2 for t in target_vec) ** 0.5

    if source_norm == 0 or target_norm == 0:
        return 0.0

    return dot_product / (source_norm * target_norm)

def structure_alignment(source_ops: List[str], target_ops: List[str]) -> float:
    """Normalized edit distance of operation sequences."""
    if not source_ops or not target_ops:
        return 0.0

    # Simple edit distance (Levenshtein)
    m, n = len(source_ops), len(target_ops)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if source_ops[i-1] == target_ops[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])

    edit_dist = dp[m][n]
    max_len = max(m, n)

    # Normalize: 1.0 = identical, 0.0 = maximally different
    return 1.0 - (edit_dist / max_len) if max_len > 0 else 0.0

def compute_reasoning_alignment(
    source_program: List[str],
    target_program: List[str]
) -> Dict[str, float]:
    """Compute all reasoning alignment metrics."""
    source_ops = extract_operations(source_program)
    target_ops = extract_operations(target_program)

    return {
        "operation_family_overlap": operation_family_overlap(source_ops, target_ops),
        "operation_multiset_similarity": operation_multiset_similarity(source_ops, target_ops),
        "structure_alignment": structure_alignment(source_ops, target_ops),
        "source_ops": source_ops,
        "target_ops": target_ops
    }

def main():
    print("=" * 80)
    print("STAGE 36: Reasoning Alignment Diagnostic")
    print("=" * 80)
    print()

    # Load retrieval cache
    cache_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/retrieval_cache.json")
    with open(cache_file) as f:
        retrieval_cache = json.load(f)

    print(f"Loaded retrieval cache for {len(retrieval_cache)} target queries")
    print()

    # Load clean cases (for gold programs)
    cases_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/cases_clean.json")
    with open(cases_file) as f:
        cases = json.load(f)

    cases_by_id = {c["source_experience_id"]: c for c in cases}

    print(f"Loaded {len(cases)} source cases")
    print()

    # Load target queries (for gold programs)
    targets_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/target_queries.json")
    with open(targets_file) as f:
        target_queries = json.load(f)

    targets_by_id = {t["id"]: t for t in target_queries}

    print(f"Loaded {len(target_queries)} target queries")
    print()

    # Compute reasoning alignment for each retrieval
    print("Computing reasoning alignment metrics...")
    print()

    alignment_results = []

    for entry in retrieval_cache:
        target_id = entry["target_id"]
        target = targets_by_id.get(target_id)

        if not target:
            continue

        target_program = target.get("qa", {}).get("program", [])

        for i, source_id in enumerate(entry["shared_source_ids"]):
            source = cases_by_id.get(source_id)

            if not source:
                continue

            source_program = source.get("program", [])
            similarity = entry["similarities"][i]

            # Compute alignment
            alignment = compute_reasoning_alignment(source_program, target_program)

            result = {
                "target_id": target_id,
                "source_id": source_id,
                "rank": i + 1,
                "semantic_similarity": similarity,
                "operation_family_overlap": alignment["operation_family_overlap"],
                "operation_multiset_similarity": alignment["operation_multiset_similarity"],
                "structure_alignment": alignment["structure_alignment"],
                "source_ops": alignment["source_ops"],
                "target_ops": alignment["target_ops"]
            }

            alignment_results.append(result)

    print(f"Computed alignment for {len(alignment_results)} retrievals")
    print()

    # Save alignment results
    alignment_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/reasoning_alignment.json")
    with open(alignment_file, 'w') as f:
        json.dump(alignment_results, f, indent=2)

    print(f"Saved alignment results to {alignment_file}")
    print()

    # Summary statistics
    print("=" * 80)
    print("REASONING ALIGNMENT SUMMARY")
    print("=" * 80)
    print()

    import numpy as np

    similarities = [r["semantic_similarity"] for r in alignment_results]
    family_overlaps = [r["operation_family_overlap"] for r in alignment_results]
    multiset_sims = [r["operation_multiset_similarity"] for r in alignment_results]
    structure_aligns = [r["structure_alignment"] for r in alignment_results]

    print("Semantic Similarity (question-only):")
    print(f"  Mean: {np.mean(similarities):.3f}")
    print(f"  Median: {np.median(similarities):.3f}")
    print(f"  Range: [{np.min(similarities):.3f}, {np.max(similarities):.3f}]")
    print()

    print("Operation Family Overlap (Jaccard):")
    print(f"  Mean: {np.mean(family_overlaps):.3f}")
    print(f"  Median: {np.median(family_overlaps):.3f}")
    print(f"  Range: [{np.min(family_overlaps):.3f}, {np.max(family_overlaps):.3f}]")
    print()

    print("Operation Multiset Similarity (Cosine):")
    print(f"  Mean: {np.mean(multiset_sims):.3f}")
    print(f"  Median: {np.median(multiset_sims):.3f}")
    print(f"  Range: [{np.min(multiset_sims):.3f}, {np.max(multiset_sims):.3f}]")
    print()

    print("Structure Alignment (Normalized Edit Distance):")
    print(f"  Mean: {np.mean(structure_aligns):.3f}")
    print(f"  Median: {np.median(structure_aligns):.3f}")
    print(f"  Range: [{np.min(structure_aligns):.3f}, {np.max(structure_aligns):.3f}]")
    print()

    # Correlation analysis
    print("=" * 80)
    print("CORRELATION ANALYSIS")
    print("=" * 80)
    print()

    from scipy.stats import spearmanr

    corr_family, _ = spearmanr(similarities, family_overlaps)
    corr_multiset, _ = spearmanr(similarities, multiset_sims)
    corr_structure, _ = spearmanr(similarities, structure_aligns)

    print("Semantic Similarity vs Reasoning Alignment:")
    print(f"  vs Operation Family Overlap: ρ = {corr_family:.3f}")
    print(f"  vs Operation Multiset Similarity: ρ = {corr_multiset:.3f}")
    print(f"  vs Structure Alignment: ρ = {corr_structure:.3f}")
    print()

    # Check if semantic and reasoning alignment are orthogonal
    if abs(corr_family) < 0.3:
        print("⚠ Semantic similarity and operation family overlap are weakly correlated")
        print("  This suggests they capture different aspects of relevance")
    else:
        print("✓ Semantic similarity and operation family overlap are moderately correlated")

    print()
    print("✓ Reasoning alignment diagnostic complete")
    print()
    print("Next step: Run minimal downstream experiment")
    print("  Script: pilot/stage36_paired_abstraction/downstream_experiment.py")

if __name__ == "__main__":
    main()
