"""
None-Only Verification: Does structured rendering coverage gain translate to downstream reasoning improvement?

Scientific Question:
    When structured rendering repairs evidence coverage (operands missing → operands present),
    does the model produce more correct answers?

Design:
    - Compare baseline 600-char HTML vs structured rendering on None arm only
    - Focus on ~20-30 strategically selected samples with high information gain
    - Same model, evaluator, prompt, temperature - only context rendering differs

Sample Selection Strategy (reproducible):
    Group A (coverage repaired, ~15 samples):
        - 600-char: missing ≥1 source operand
        - Structured: all source operands present
        - Baseline prediction: 'N/A', 'not determinable', or wrong extraction

    Group B (control, ~5-10 samples):
        - 600-char: already full coverage
        - Should show no change or minimal change

    Avoid: Cherry-picking based on expected results

Analysis:
    Per-sample comparison:
        1. coverage repaired → answer becomes correct
        2. coverage repaired → extraction improves but operation still wrong
        3. coverage repaired → still fails (extraction or reasoning)
        4. coverage complete → no change
        5. regression (if any)

    Failure mode shift:
        Baseline errors: missing evidence, N/A, wrong extraction
        After repair: operation/reasoning errors, scale/unit errors, format errors

Constraints:
    - No Case/Strategy/Both arms
    - No retrieval optimization
    - No prompt modification
    - No evaluator changes
    - No simultaneous confounds
"""

import json
import os
import re
import sys

import pyarrow.parquet as pq

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pilot"))

from multibench.context_representation_ablation import (
    extract_source_operands,
    normalize_numeric_forms,
)


def load_baseline_cache(cache_path: str) -> dict[str, dict]:
    """Load Stage 33 baseline (600-char HTML, None arm) predictions."""
    records = {}
    with open(cache_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                if rec["arm"] == "none":
                    records[rec["uid"]] = rec
    return records


def compute_coverage_comparison(
    uid: str,
    gold_program: str,
    baseline_context: str,
    structured_context: str,
) -> dict:
    """Compare operand coverage between baseline and structured rendering."""
    operands = extract_source_operands(gold_program)
    if not operands:
        return {"operands": [], "baseline_coverage": 1.0, "structured_coverage": 1.0}

    # Normalize contexts for matching
    baseline_norm = normalize_numeric_forms(baseline_context)
    structured_norm = normalize_numeric_forms(structured_context)

    baseline_found = sum(1 for op in operands if op in baseline_norm)
    structured_found = sum(1 for op in operands if op in structured_norm)

    return {
        "operands": operands,
        "baseline_coverage": baseline_found / len(operands),
        "structured_coverage": structured_found / len(operands),
        "baseline_missing": len(operands) - baseline_found,
        "structured_missing": len(operands) - structured_found,
    }


def select_verification_samples(
    cache_path: str,
    validation_parquet: str,
    target_group_a: int = 15,
    target_group_b: int = 10,
) -> dict:
    """
    Select samples for None-only verification.

    Group A: Coverage repaired (baseline incomplete → structured complete)
    Group B: Control (baseline already complete)

    Returns:
        {
            "group_a": [uid, ...],  # coverage repaired
            "group_b": [uid, ...],  # control
            "metadata": {uid: {...}}
        }
    """
    # Load baseline predictions
    baseline_cache = load_baseline_cache(cache_path)

    # Load validation data
    val_table = pq.read_table(validation_parquet)
    gold_by_uid = {row["uid"]: row for row in val_table.to_pylist()}

    # Load ablation results to determine coverage status
    from multibench.multihiertt_four_arm_dry_run import render_context as render_baseline

    # Import structured rendering
    sys.path.insert(0, os.path.dirname(__file__))
    from multihiertt_four_arm_dry_run import render_structured_table

    def render_structured_context(row):
        """Render context with structured table."""
        paragraphs = []
        for i, text in enumerate((row.get("paragraphs") or [])[:30]):
            from multihiertt_four_arm_dry_run import normalize_text
            t = normalize_text(text)
            if len(t) > 300:
                t = t[:300].rstrip() + "..."
            paragraphs.append(f"p{i}: {t}")
        table_bits = []
        for i, html in enumerate((row.get("tables") or [])[:6]):
            table_bits.append(f"table_{i}:\n{render_structured_table(html, char_limit=2000)}")
        return "\n".join([
            "Paragraphs (selected):",
            "\n".join(paragraphs) or "(none)",
            "",
            "Tables (structured):",
            "\n".join(table_bits) or "(none)",
        ]).strip()

    candidates_a = []  # coverage repaired
    candidates_b = []  # control (already complete)
    metadata = {}

    for uid, rec in baseline_cache.items():
        gold = gold_by_uid.get(uid)
        if not gold:
            continue

        program = gold.get("program", "")
        if not program:
            continue

        # Render both contexts
        baseline_ctx = render_baseline(gold)
        structured_ctx = render_structured_context(gold)

        # Compute coverage
        cov = compute_coverage_comparison(uid, program, baseline_ctx, structured_ctx)

        # Check baseline prediction quality
        answer = rec.get("answer")
        is_na_or_fail = (
            answer is None
            or str(answer).lower() in ["n/a", "not determinable", "not enough information"]
            or str(answer) == ""
        )

        # Group A: coverage repaired
        if cov["baseline_coverage"] < 1.0 and cov["structured_coverage"] == 1.0:
            candidates_a.append({
                "uid": uid,
                "question": gold.get("question", ""),
                "program": program,
                "gold_answer": gold.get("answer"),
                "baseline_answer": answer,
                "is_na_or_fail": is_na_or_fail,
                "baseline_coverage": cov["baseline_coverage"],
                "operands": list(cov["operands"]),  # Convert set to list
                "baseline_missing": cov["baseline_missing"],
            })

        # Group B: control (already complete coverage)
        elif cov["baseline_coverage"] == 1.0 and cov["structured_coverage"] == 1.0:
            candidates_b.append({
                "uid": uid,
                "question": gold.get("question", ""),
                "program": program,
                "gold_answer": gold.get("answer"),
                "baseline_answer": answer,
                "is_na_or_fail": is_na_or_fail,
                "baseline_coverage": 1.0,
                "operands": list(cov["operands"]),  # Convert set to list
            })

        metadata[uid] = {
            "baseline_coverage": cov["baseline_coverage"],
            "structured_coverage": cov["structured_coverage"],
            "operands": list(cov["operands"]),  # Convert set to list for JSON
            "baseline_answer": answer,
            "gold_answer": gold.get("answer"),
        }

    # Sort Group A by: is_na_or_fail first, then by most operands missing
    candidates_a.sort(key=lambda x: (-int(x["is_na_or_fail"]), -x["baseline_missing"]))

    # Take top samples
    selected_a = [x["uid"] for x in candidates_a[:target_group_a]]
    selected_b = [x["uid"] for x in candidates_b[:target_group_b]]

    return {
        "group_a": selected_a,
        "group_b": selected_b,
        "metadata": metadata,
        "candidates_a_full": candidates_a,
        "candidates_b_full": candidates_b,
    }


if __name__ == "__main__":
    cache_path = os.path.join(
        ROOT,
        "pilot/multibench/output/multihiertt/multihiertt_four_arm_dry_run_repaired_cache.jsonl",
    )
    validation_path = os.path.join(ROOT, "data/multihiertt/raw/validation.parquet")

    selection = select_verification_samples(cache_path, validation_path)

    print(f"Group A (coverage repaired): {len(selection['group_a'])} samples")
    print(f"Group B (control): {len(selection['group_b'])} samples")
    print(f"Total: {len(selection['group_a']) + len(selection['group_b'])} samples")
    print()

    print("Group A samples (coverage repaired):")
    for i, uid in enumerate(selection["group_a"][:10], 1):
        meta = selection["metadata"][uid]
        cand = next(c for c in selection["candidates_a_full"] if c["uid"] == uid)
        print(f"  {i}. {uid[:8]}... baseline_cov={meta['baseline_coverage']:.2f}, "
              f"missing={cand['baseline_missing']}, is_na={cand['is_na_or_fail']}")

    print()
    print("Group B samples (control, already complete):")
    for i, uid in enumerate(selection["group_b"][:5], 1):
        meta = selection["metadata"][uid]
        print(f"  {i}. {uid[:8]}... baseline_cov={meta['baseline_coverage']:.2f}")

    # Save selection for verification run
    output_path = os.path.join(ROOT, "pilot/multibench/none_only_verification_samples.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "group_a": selection["group_a"],
                "group_b": selection["group_b"],
                "metadata": selection["metadata"],
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"\nSaved to: {output_path}")
