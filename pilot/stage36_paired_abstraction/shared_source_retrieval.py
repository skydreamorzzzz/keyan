"""Shared-source retrieval protocol for paired abstraction experiment.

Key principle: All representation arms (Case, Strategy, Paired) must use IDENTICAL
source experience IDs for each target query. This isolates representation effect.

Retrieval method: Question-only embedding similarity (representation-neutral).
"""
import json
import os
import sys
from typing import List, Dict

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from pilot.embeddings import get_embedding

def load_clean_sources():
    """Load QC-passed Case and Strategy pairs."""
    cases_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/cases_clean.json")
    strategies_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/strategies_clean.json")

    with open(cases_file) as f:
        cases = json.load(f)

    with open(strategies_file) as f:
        strategies = json.load(f)

    # Verify pairing
    case_ids = {c["source_experience_id"] for c in cases}
    strategy_ids = {s["source_experience_id"] for s in strategies}

    assert case_ids == strategy_ids, "Case and Strategy IDs must match"

    return cases, strategies

def compute_question_embeddings(cases: List[Dict]):
    """Compute embeddings for source questions (representation-neutral)."""
    embeddings = []

    print("Computing source question embeddings...")
    for i, case in enumerate(cases):
        if i % 20 == 0:
            print(f"  Progress: {i}/{len(cases)}")

        question = case["question"]
        emb = get_embedding(question)
        embeddings.append(emb)

    print(f"  Computed {len(embeddings)} embeddings")
    return np.array(embeddings)

def retrieve_shared_sources(
    target_question: str,
    source_questions: List[str],
    source_embeddings: np.ndarray,
    top_k: int = 3
) -> List[int]:
    """Retrieve top-k source experience indices using question similarity.

    Returns indices, NOT source IDs, to ensure all arms use identical sources.
    """
    # Compute target embedding
    target_emb = get_embedding(target_question)

    # Compute cosine similarities
    similarities = np.dot(source_embeddings, target_emb) / (
        np.linalg.norm(source_embeddings, axis=1) * np.linalg.norm(target_emb)
    )

    # Get top-k indices
    top_indices = np.argsort(similarities)[::-1][:top_k]

    return top_indices.tolist(), similarities[top_indices].tolist()

def build_retrieval_cache(
    target_queries: List[Dict],
    source_cases: List[Dict],
    source_embeddings: np.ndarray,
    top_k: int = 3
):
    """Build retrieval cache mapping each target to shared source indices."""
    cache = []

    print(f"Building retrieval cache for {len(target_queries)} target queries...")
    print()

    source_questions = [c["question"] for c in source_cases]

    for i, target in enumerate(target_queries):
        if i % 10 == 0 and i > 0:
            print(f"  Progress: {i}/{len(target_queries)}")

        target_question = target["qa"]["question"]

        # Retrieve shared sources
        indices, similarities = retrieve_shared_sources(
            target_question,
            source_questions,
            source_embeddings,
            top_k=top_k
        )

        # Map indices to source IDs
        source_ids = [source_cases[idx]["source_experience_id"] for idx in indices]

        cache_entry = {
            "target_id": target["id"],
            "target_question": target_question,
            "shared_source_ids": source_ids,
            "source_indices": indices,
            "similarities": similarities
        }

        cache.append(cache_entry)

    print(f"  Built cache for {len(cache)} target queries")
    print()

    return cache

def main():
    print("=" * 80)
    print("STAGE 36: Shared-Source Retrieval Protocol")
    print("=" * 80)
    print()

    # Load clean sources
    cases, strategies = load_clean_sources()
    print(f"Loaded {len(cases)} clean Case/Strategy pairs")
    print()

    # Compute source embeddings (question-only, representation-neutral)
    source_embeddings = compute_question_embeddings(cases)
    print()

    # Save source embeddings for reproducibility
    embeddings_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/source_embeddings.npy")
    np.save(embeddings_file, source_embeddings)
    print(f"Saved source embeddings to {embeddings_file}")
    print()

    # Load target queries (FinQA dev set, will select subset)
    dev_file = os.path.join(ROOT, "data/finqa/dev.json")
    with open(dev_file) as f:
        dev_samples = json.load(f)

    print(f"Loaded {len(dev_samples)} dev samples")
    print()

    # Select 30 diverse target queries for pilot
    # Use stratified sampling across operation families
    from collections import defaultdict

    family_samples = defaultdict(list)
    for sample in dev_samples:
        program = sample.get("qa", {}).get("program", [])
        if not program:
            continue

        # Extract first operation as rough family indicator
        first_op = program[0].split("(")[0] if program else "unknown"
        family_samples[first_op].append(sample)

    # Sample 30 queries with diversity
    np.random.seed(42)
    target_queries = []

    # Get most common families
    families = sorted(family_samples.keys(), key=lambda f: len(family_samples[f]), reverse=True)

    samples_per_family = 30 // len(families[:6])  # Top 6 families

    for family in families[:6]:
        available = family_samples[family]
        n_sample = min(samples_per_family, len(available))
        sampled = np.random.choice(len(available), size=n_sample, replace=False)
        target_queries.extend([available[i] for i in sampled])

    # Fill remainder randomly
    while len(target_queries) < 30:
        remaining = [s for s in dev_samples if s not in target_queries]
        target_queries.append(np.random.choice(remaining))

    target_queries = target_queries[:30]

    print(f"Selected {len(target_queries)} diverse target queries")
    print()

    # Build retrieval cache with top-3 sources per target
    retrieval_cache = build_retrieval_cache(
        target_queries,
        cases,
        source_embeddings,
        top_k=3
    )

    # Save retrieval cache
    cache_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/retrieval_cache.json")
    with open(cache_file, 'w') as f:
        json.dump(retrieval_cache, f, indent=2)

    print(f"Saved retrieval cache to {cache_file}")
    print()

    # Save target queries
    targets_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/target_queries.json")
    with open(targets_file, 'w') as f:
        json.dump(target_queries, f, indent=2)

    print(f"Saved target queries to {targets_file}")
    print()

    # Diagnostic: Check semantic relevance distribution
    print("=" * 80)
    print("SEMANTIC RELEVANCE DIAGNOSTIC")
    print("=" * 80)
    print()

    all_similarities = [s for entry in retrieval_cache for s in entry["similarities"]]

    print(f"Top-3 retrieval similarities:")
    print(f"  Mean: {np.mean(all_similarities):.3f}")
    print(f"  Median: {np.median(all_similarities):.3f}")
    print(f"  Min: {np.min(all_similarities):.3f}")
    print(f"  Max: {np.max(all_similarities):.3f}")
    print()

    # Check for same-question retrieval (should be rare in dev)
    exact_matches = 0
    for entry in retrieval_cache:
        target_q = entry["target_question"].lower()
        for idx in entry["source_indices"]:
            source_q = cases[idx]["question"].lower()
            if target_q == source_q:
                exact_matches += 1

    print(f"Exact question matches: {exact_matches} / {len(retrieval_cache) * 3} ({exact_matches/(len(retrieval_cache)*3)*100:.1f}%)")
    print()

    print("✓ Shared-source retrieval protocol complete")
    print()
    print("Next step: Reasoning alignment diagnostic")
    print("  Script: pilot/stage36_paired_abstraction/reasoning_alignment.py")

if __name__ == "__main__":
    main()
