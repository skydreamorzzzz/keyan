"""None-only verification experiment: Re-run selected samples with structured rendering.

Validates causal claim: evidence coverage improvement → downstream performance improvement.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import sys
import time
from typing import Any, Dict

import pyarrow.parquet as pq

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "pilot"))

from pilot.llm import call_once_with_metadata
from pilot.multibench.multihiertt_evaluator import evaluate_one
from pilot.multibench.none_only_verification_runner import render_context_structured_2000char


def normalize_text(text: str) -> str:
    return " ".join(text.split())


def build_prompt(gold_row: Dict[str, Any]) -> str:
    """Build prompt with structured rendering (same as modified multihiertt_four_arm_dry_run.py)."""
    question = normalize_text(gold_row.get("question", ""))
    context = render_context_structured_2000char(gold_row)

    return f"""You are a financial reasoning assistant. Answer the question based on the provided context.

Context:
{context}

Question: {question}

Instructions:
- Extract relevant values from tables/paragraphs
- If the question asks for a calculation (sum, difference, growth rate, average), perform it
- Return only the final numeric answer (as a number or percentage)
- If the answer cannot be determined, return "N/A"

Answer:"""


def run_one_sample(gold_row: Dict[str, Any], cache_path: str) -> Dict[str, Any]:
    """Run inference for one sample with structured rendering."""
    uid = gold_row["uid"]
    prompt = build_prompt(gold_row)

    # Generate cache key
    key_data = f"none_verification_structured_v1:{uid}:{prompt}"
    key = hashlib.sha256(key_data.encode()).hexdigest()[:16]

    # Check cache
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            for line in f:
                if line.strip():
                    cached = json.loads(line)
                    if cached.get("key") == key:
                        return cached

    # Call LLM
    try:
        result = call_once_with_metadata(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1400,
            temperature=0,
        )

        raw_response = result.get("text", "")
        answer = raw_response.strip()

        # Evaluate
        eval_result = evaluate_one(gold_row, {"answer": answer})

        record = {
            "key": key,
            "uid": uid,
            "arm": "none",
            "rendering": "structured",
            "raw_response": raw_response,
            "answer": answer,
            "gold_answer": gold_row.get("answer"),
            "em": eval_result.get("em", 0.0),
            "f1": eval_result.get("f1", 0.0),
            "runtime": result.get("runtime", {}),
        }

        # Append to cache with file lock
        import fcntl
        with open(cache_path, "a") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        return record

    except Exception as e:
        print(f"Error on {uid}: {e}")
        return {
            "key": key,
            "uid": uid,
            "arm": "none",
            "rendering": "structured",
            "error": str(e),
        }


def main():
    # Load selection
    selection_path = os.path.join(ROOT, "pilot/multibench/none_only_verification_samples.json")
    with open(selection_path) as f:
        selection = json.load(f)

    group_a = selection["group_a"]
    group_b = selection["group_b"]
    all_samples = group_a + group_b

    print(f"Loaded {len(all_samples)} samples for verification")
    print(f"  Group A (coverage repaired): {len(group_a)}")
    print(f"  Group B (control): {len(group_b)}")

    # Load validation data
    val_table = pq.read_table(os.path.join(ROOT, "data/multihiertt/raw/validation.parquet"))
    gold_by_uid = {row["uid"]: row for row in val_table.to_pylist()}

    # Prepare cache
    cache_path = os.path.join(
        ROOT, "pilot/multibench/output/multihiertt/none_only_verification_cache.jsonl"
    )
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)

    # Run with concurrency
    CONCURRENCY = 8

    def run_with_uid(sample_meta):
        uid = sample_meta["uid"]
        gold = gold_by_uid.get(uid)
        if not gold:
            print(f"Warning: {uid} not found in validation set")
            return None
        return run_one_sample(gold, cache_path)

    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        results = list(executor.map(run_with_uid, all_samples))
    elapsed = time.time() - start

    # Filter valid results
    valid_results = [r for r in results if r and "error" not in r]

    print(f"\nCompleted {len(valid_results)}/{len(all_samples)} samples in {elapsed:.1f}s")
    print(f"Cache: {cache_path}")

    # Quick stats
    group_a_uids = {s["uid"] for s in group_a}
    group_a_results = [r for r in valid_results if r["uid"] in group_a_uids]
    group_b_results = [r for r in valid_results if r["uid"] not in group_a_uids]

    em_a = sum(r["em"] for r in group_a_results) / len(group_a_results) if group_a_results else 0
    em_b = sum(r["em"] for r in group_b_results) / len(group_b_results) if group_b_results else 0

    print(f"\nQuick stats (structured rendering):")
    print(f"  Group A EM: {em_a:.3f} ({sum(r['em'] for r in group_a_results)}/{len(group_a_results)})")
    print(f"  Group B EM: {em_b:.3f} ({sum(r['em'] for r in group_b_results)}/{len(group_b_results)})")


if __name__ == "__main__":
    main()
