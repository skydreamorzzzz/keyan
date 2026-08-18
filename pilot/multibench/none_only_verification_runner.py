"""None-only verification: Does structured rendering improve downstream performance?

Scientific question: When structured rendering repairs evidence coverage (incomplete → complete),
does the model produce better answers?

Design:
- Select 20-30 samples where coverage changes from incomplete to complete
- Re-run with structured rendering (none arm only)
- Compare against baseline (600-char HTML) predictions from Stage 33 cache
- Classify outcome: coverage_repair → correct_answer vs still_wrong

Constraint: No other changes (same model, temp, evaluator, prompt structure)
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict

import pyarrow.parquet as pq

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "pilot"))

from pilot.multibench.context_representation_ablation import (
    extract_source_operands,
    normalize_numeric_forms,
    render_structured_table,
)


def render_context_baseline_600char(row: Dict[str, Any]) -> str:
    """Original Stage 33 baseline: 600-char HTML preview per table."""
    def normalize_text(text: str) -> str:
        return " ".join(text.split())

    def render_table_html_preview(html: str, limit: int = 600) -> str:
        return normalize_text(html)[:limit]

    paragraphs = []
    for i, text in enumerate((row.get("paragraphs") or [])[:30]):
        t = normalize_text(text)
        if len(t) > 300:
            t = t[:300].rstrip() + "..."
        paragraphs.append(f"p{i}: {t}")

    table_bits = []
    for i, html in enumerate((row.get("tables") or [])[:6]):
        table_bits.append(f"table_{i}: {render_table_html_preview(html, limit=600)}")

    return "\n".join([
        "Paragraphs (selected):",
        "\n".join(paragraphs) or "(none)",
        "",
        "Tables (previews):",
        "\n".join(table_bits) or "(none)",
    ]).strip()


def render_context_structured_2000char(row: Dict[str, Any]) -> str:
    """New structured rendering: 2000-char structured table per table."""
    def normalize_text(text: str) -> str:
        return " ".join(text.split())

    paragraphs = []
    for i, text in enumerate((row.get("paragraphs") or [])[:30]):
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


def compute_coverage(gold_row: Dict, rendered_context: str) -> Dict:
    """Compute operand coverage."""
    program = gold_row.get("program", "")
    if not program:
        return {"has_program": False}

    operands = extract_source_operands(program)
    if not operands:
        return {"has_program": True, "has_operands": False}

    context_norm = normalize_numeric_forms(rendered_context)
    found = sum(1 for op in operands if op in context_norm)

    return {
        "has_program": True,
        "has_operands": True,
        "operands": operands,
        "found": found,
        "total": len(operands),
        "coverage": found / len(operands),
        "is_complete": found == len(operands),
    }


def main():
    # Load validation data
    val_table = pq.read_table(os.path.join(ROOT, "data/multihiertt/raw/validation.parquet"))
    gold_by_uid = {row["uid"]: row for row in val_table.to_pylist()}

    # Load Stage 33 cache (baseline predictions)
    cache_path = os.path.join(
        ROOT, "pilot/multibench/output/multihiertt/multihiertt_four_arm_dry_run_repaired_cache.jsonl"
    )
    cache = []
    with open(cache_path) as f:
        for line in f:
            if line.strip():
                cache.append(json.loads(line))

    none_records = [r for r in cache if r["arm"] == "none"]
    print(f"Loaded {len(none_records)} none-arm records from Stage 33 cache")

    # For each sample, compute coverage under both renderings
    candidates = []
    for rec in none_records:
        uid = rec["uid"]
        gold = gold_by_uid.get(uid)
        if not gold:
            continue

        program = gold.get("program", "")
        if not program:
            continue

        # Render both versions
        baseline_ctx = render_context_baseline_600char(gold)
        structured_ctx = render_context_structured_2000char(gold)

        # Compute coverage
        baseline_cov = compute_coverage(gold, baseline_ctx)
        structured_cov = compute_coverage(gold, structured_ctx)

        if not baseline_cov.get("has_operands"):
            continue

        # Classify
        baseline_complete = baseline_cov["is_complete"]
        structured_complete = structured_cov["is_complete"]
        baseline_answer = rec["answer"]
        gold_answer = gold.get("answer")

        # Check if baseline gave up
        is_na_or_fail = False
        if baseline_answer:
            ans_lower = str(baseline_answer).lower().strip()
            is_na_or_fail = any(
                keyword in ans_lower
                for keyword in ["n/a", "not enough", "cannot", "unable", "not determinable"]
            )

        candidates.append({
            "uid": uid,
            "program": program,
            "question": gold.get("question", "")[:80],
            "baseline_complete": baseline_complete,
            "structured_complete": structured_complete,
            "baseline_coverage": baseline_cov["coverage"],
            "structured_coverage": structured_cov["coverage"],
            "baseline_answer": baseline_answer,
            "gold_answer": gold_answer,
            "is_na_or_fail": is_na_or_fail,
            "operands": list(baseline_cov["operands"]),
        })

    print(f"\nTotal samples with programs: {len(candidates)}")

    # Group A: coverage repaired (incomplete → complete)
    group_a = [
        c for c in candidates
        if not c["baseline_complete"] and c["structured_complete"]
    ]

    # Group B: control (already complete)
    group_b = [
        c for c in candidates
        if c["baseline_complete"] and c["structured_complete"]
    ]

    print(f"\nGroup A (coverage repaired): {len(group_a)} samples")
    print(f"Group B (control, already complete): {len(group_b)} samples")

    # Select samples for verification
    # Priority for Group A: those where baseline gave N/A
    group_a_priority = sorted(
        group_a,
        key=lambda c: (-int(c["is_na_or_fail"]), c["baseline_coverage"])
    )

    # Select up to 20 from Group A, 10 from Group B
    selected_a = group_a_priority[:20]
    selected_b = group_b[:10]

    print(f"\nSelected for verification:")
    print(f"  Group A: {len(selected_a)} samples")
    print(f"  Group B: {len(selected_b)} samples")
    print(f"  Total: {len(selected_a) + len(selected_b)} samples")

    # Show examples
    print(f"\nGroup A examples (coverage repaired):")
    for i, c in enumerate(selected_a[:5], 1):
        print(f"  {i}. {c['uid'][:8]}... baseline_cov={c['baseline_coverage']:.2f}, "
              f"is_na={c['is_na_or_fail']}")
        print(f"     Q: {c['question']}")
        print(f"     Baseline answer: {c['baseline_answer']}")
        print()

    print(f"Group B examples (control):")
    for i, c in enumerate(selected_b[:5], 1):
        print(f"  {i}. {c['uid'][:8]}... baseline_cov=1.00")

    # Save selection
    output = {
        "group_a": selected_a,
        "group_b": selected_b,
        "metadata": {
            "total_samples": len(candidates),
            "group_a_total": len(group_a),
            "group_b_total": len(group_b),
            "selected_a": len(selected_a),
            "selected_b": len(selected_b),
        },
    }

    output_path = os.path.join(
        ROOT, "pilot/multibench/none_only_verification_samples.json"
    )
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()
