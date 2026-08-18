"""Pipeline validity audit for MultiHiertt Stage 33.

Diagnostic goals:
1. Why is baseline (none) EM only 0.117?
2. Are HTML tables truncated too aggressively?
3. Is the evaluator failing to match valid answers?
4. What are the failure modes?
"""
import json
import os
from collections import Counter, defaultdict

CACHE_PATH = "pilot/multibench/output/multihiertt/multihiertt_four_arm_dry_run_repaired_cache.jsonl"
VAL_PATH = "data/multihiertt/raw/validation.parquet"


def load_cache():
    """Load all cache records."""
    records = []
    with open(CACHE_PATH) as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def load_validation():
    """Load validation set from parquet."""
    import pyarrow.parquet as pq
    tbl = pq.read_table(VAL_PATH)
    rows = []
    for i in range(tbl.num_rows):
        row = {col: tbl[col][i].as_py() for col in tbl.column_names}
        rows.append(row)
    return {row["uid"]: row for row in rows}


def extract_messages_from_key(key_obj):
    """Extract input messages from cache key if stored."""
    # The key is a hash, but we have uid+arm in the cache record
    # We need to reconstruct the prompt to analyze it
    return None


def compute_exact_match(pred, gold) -> bool:
    """Exact match evaluator from the script."""
    def norm(x):
        if isinstance(x, list):
            return tuple(sorted(str(v).strip().lower() for v in x))
        return str(x).strip().lower()
    return norm(pred) == norm(gold)


def classify_failure(cache_rec, gold_row):
    """Classify failure mode for a single record."""
    pred = cache_rec.get("answer")
    gold = gold_row.get("answer")

    # Type mismatch
    pred_type = type(pred).__name__
    gold_type = type(gold).__name__

    if pred_type != gold_type:
        return f"type_mismatch_{gold_type}_to_{pred_type}"

    # Numeric comparison
    if isinstance(gold, (int, float)) and isinstance(pred, (int, float)):
        ratio = abs(pred / gold) if gold != 0 else float('inf')
        if 0.95 <= ratio <= 1.05:
            return "numeric_close"
        if ratio < 0.1 or ratio > 10:
            return "numeric_scale_error"
        return "numeric_wrong_value"

    # String comparison
    if isinstance(gold, str) and isinstance(pred, str):
        g = gold.strip().lower()
        p = pred.strip().lower()
        if g in p or p in g:
            return "string_partial_match"
        return "string_no_match"

    # List comparison
    if isinstance(gold, list) and isinstance(pred, list):
        if len(gold) != len(pred):
            return f"list_length_mismatch_{len(gold)}_vs_{len(pred)}"
        return "list_wrong_elements"

    return "other"


def analyze_by_answer_type(cache_records, val_data):
    """Break down failures by answer_type."""
    by_type = defaultdict(lambda: {"total": 0, "correct": 0, "failures": []})

    for rec in cache_records:
        if rec["arm"] != "none":
            continue

        uid = rec["uid"]
        gold_row = val_data.get(uid)
        if not gold_row:
            continue

        ans_type = gold_row.get("answer_type", "unknown")
        pred = rec.get("answer")
        gold = gold_row.get("answer")

        by_type[ans_type]["total"] += 1

        is_correct = compute_exact_match(pred, gold)
        if is_correct:
            by_type[ans_type]["correct"] += 1
        else:
            failure_mode = classify_failure(rec, gold_row)
            by_type[ans_type]["failures"].append({
                "uid": uid,
                "mode": failure_mode,
                "pred": pred,
                "gold": gold,
                "question": gold_row.get("question", "")[:100],
            })

    return by_type


def analyze_context_truncation(val_data, sample_uids):
    """Check if HTML tables are heavily truncated."""
    truncation_stats = []

    for uid in sample_uids:
        row = val_data.get(uid)
        if not row:
            continue

        tables = row.get("tables", [])
        total_html_len = sum(len(t) for t in tables)

        # Simulate the render_context truncation
        rendered_len = 0
        for html in tables[:6]:  # max 6 tables
            rendered_len += min(600, len(html.replace("\n", " ")))

        truncation_stats.append({
            "uid": uid,
            "n_tables": len(tables),
            "total_html_chars": total_html_len,
            "rendered_chars": rendered_len,
            "truncation_ratio": rendered_len / total_html_len if total_html_len > 0 else 1.0,
        })

    return truncation_stats


def main():
    print("Loading data...")
    cache_records = load_cache()
    val_data = load_validation()

    print(f"Cache records: {len(cache_records)}")
    print(f"Validation samples: {len(val_data)}")

    # Get unique UIDs from none arm
    none_records = [r for r in cache_records if r["arm"] == "none"]
    sample_uids = [r["uid"] for r in none_records]

    print(f"\n=== Baseline (none arm) Analysis ===")
    print(f"Samples: {len(sample_uids)}")

    # Failure breakdown
    print("\n--- Failure Mode Classification ---")
    by_type = analyze_by_answer_type(cache_records, val_data)

    for ans_type, stats in sorted(by_type.items()):
        em = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
        print(f"\n{ans_type}: {stats['correct']}/{stats['total']} = {em:.3f}")

        # Count failure modes
        mode_counts = Counter(f["mode"] for f in stats["failures"])
        for mode, count in mode_counts.most_common():
            print(f"  {mode}: {count}")

    # Show sample failures
    print("\n--- Sample Failures (none arm) ---")
    all_failures = []
    for ans_type, stats in by_type.items():
        all_failures.extend(stats["failures"][:3])

    for i, f in enumerate(all_failures[:10]):
        print(f"\n{i+1}. {f['mode']}")
        print(f"   Q: {f['question']}")
        print(f"   Gold: {f['gold']} ({type(f['gold']).__name__})")
        print(f"   Pred: {f['pred']} ({type(f['pred']).__name__})")

    # Context truncation analysis
    print("\n\n=== Context Truncation Analysis ===")
    trunc_stats = analyze_context_truncation(val_data, sample_uids[:20])

    avg_trunc = sum(s["truncation_ratio"] for s in trunc_stats) / len(trunc_stats)
    print(f"Average truncation ratio: {avg_trunc:.3f}")
    print(f"(ratio = rendered_chars / total_html_chars)")

    severe_trunc = [s for s in trunc_stats if s["truncation_ratio"] < 0.3]
    print(f"Samples with <30% HTML preserved: {len(severe_trunc)}/{len(trunc_stats)}")

    for s in severe_trunc[:5]:
        print(f"  uid={s['uid'][:16]}... {s['n_tables']} tables, "
              f"{s['total_html_chars']} chars -> {s['rendered_chars']} chars "
              f"({s['truncation_ratio']:.1%})")

    print("\n=== Recommendation ===")
    if avg_trunc < 0.4:
        print("HYPOTHESIS: Aggressive HTML truncation likely causes evidence loss.")
        print("NEXT STEP: Increase table preview limit or parse HTML to structured text.")
    else:
        print("Truncation ratio acceptable. Focus on other failure modes.")


if __name__ == "__main__":
    main()
