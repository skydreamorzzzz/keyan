"""Retrieve shared sources for 194 new expanded queries.

Uses frozen retrieval protocol from pilot:
- Question-only embedding similarity (representation-neutral)
- Top-k=3 sources per target
- Same source embeddings as pilot (78 Case/Strategy pairs)
"""
import json
import os
import sys
from typing import List, Dict

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from pilot.embeddings import get_embedding

def retrieve_shared_sources(
    target_question: str,
    source_embeddings: np.ndarray,
    top_k: int = 3
) -> tuple:
    """Retrieve top-k source experience indices using question similarity."""
    target_emb = get_embedding(target_question)

    # Compute cosine similarities
    similarities = np.dot(source_embeddings, target_emb) / (
        np.linalg.norm(source_embeddings, axis=1) * np.linalg.norm(target_emb)
    )

    # Get top-k indices
    top_indices = np.argsort(similarities)[::-1][:top_k]

    return top_indices.tolist(), similarities[top_indices].tolist()

def main():
    print("=" * 80)
    print("Retrieve Shared Sources for 194 Expanded Queries")
    print("=" * 80)
    print()

    # Load expanded sample
    expanded_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/expanded_sample_queries.json")
    with open(expanded_file) as f:
        expanded = json.load(f)

    # Filter to new queries only (not pilot)
    new_queries = [q for q in expanded if not q.get("is_pilot", False)]
    print(f"Loaded {len(new_queries)} new queries (non-pilot)")
    print()

    # Load source embeddings (frozen from pilot)
    embeddings_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/source_embeddings.npy")
    source_embeddings = np.load(embeddings_file)
    print(f"Loaded source embeddings: {source_embeddings.shape}")
    print()

    # Load source cases for ID mapping
    cases_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/paired_sources.json")
    with open(cases_file) as f:
        cases = json.load(f)

    print(f"Loaded {len(cases)} source cases")
    print()

    # Build retrieval cache for new queries
    print(f"Retrieving shared sources (k=3) for {len(new_queries)} queries...")
    print()

    retrieval_cache = []

    for i, query in enumerate(new_queries):
        if i > 0 and i % 20 == 0:
            print(f"  Progress: {i}/{len(new_queries)}")

        target_question = query["qa"]["question"]
        target_id = query["id"]

        # Retrieve shared sources using frozen protocol
        indices, similarities = retrieve_shared_sources(
            target_question,
            source_embeddings,
            top_k=3
        )

        # Map indices to source IDs
        source_ids = [cases[idx]["source_experience_id"] for idx in indices]

        cache_entry = {
            "target_id": target_id,
            "target_question": target_question,
            "shared_source_ids": source_ids,
            "source_indices": indices,
            "similarities": similarities
        }

        retrieval_cache.append(cache_entry)

    print(f"  Completed: {len(retrieval_cache)}/{len(new_queries)}")
    print()

    # Save retrieval cache for new queries
    output_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/expanded_retrieval_cache.json")
    with open(output_file, 'w') as f:
        json.dump(retrieval_cache, f, indent=2)

    print(f"✓ Saved retrieval cache to {output_file}")
    print()

    # Diagnostic: Check semantic relevance distribution
    all_similarities = [s for entry in retrieval_cache for s in entry["similarities"]]

    print("Semantic relevance diagnostic:")
    print(f"  Mean: {np.mean(all_similarities):.3f}")
    print(f"  Median: {np.median(all_similarities):.3f}")
    print(f"  Min: {np.min(all_similarities):.3f}")
    print(f"  Max: {np.max(all_similarities):.3f}")
    print()

    print("✓ Retrieval complete for 194 new queries")

if __name__ == "__main__":
    main()
