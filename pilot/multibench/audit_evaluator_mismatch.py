"""Deep dive into evaluator mismatch: why are type-correct numeric answers marked wrong?

Focus: The 3 samples where pred is numerically close but marked wrong due to type mismatch.
"""
import json
import pyarrow.parquet as pq

CACHE_PATH = "pilot/multibench/output/multihiertt/multihiertt_four_arm_dry_run_repaired_cache.jsonl"
VAL_PATH = "data/multihiertt/raw/validation.parquet"


def load_cache():
    records = []
    with open(CACHE_PATH) as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def load_validation():
    tbl = pq.read_table(VAL_PATH)
    rows = []
    for i in range(tbl.num_rows):
        row = {col: tbl[col][i].as_py() for col in tbl.column_names}
        rows.append(row)
    return {row["uid"]: row for row in rows}


def normalize_answer(ans):
    """Mimic the evaluator's normalization."""
    if isinstance(ans, list):
        return tuple(sorted(str(v).strip().lower() for v in ans))
    return str(ans).strip().lower()


def main():
    cache = load_cache()
    val_data = load_validation()

    # Focus on type mismatch failures
    type_mismatches = []
    for rec in cache:
        if rec["arm"] != "none":
            continue

        uid = rec["uid"]
        gold_row = val_data.get(uid)
        if not gold_row:
            continue

        pred = rec.get("answer")
        gold = gold_row.get("answer")

        pred_type = type(pred).__name__
        gold_type = type(gold).__name__

        if pred_type != gold_type and gold_type in ("str", "int", "float"):
            type_mismatches.append({
                "uid": uid,
                "pred": pred,
                "pred_type": pred_type,
                "gold": gold,
                "gold_type": gold_type,
                "question": gold_row.get("question", ""),
                "program": gold_row.get("program", ""),
                "answer_type": gold_row.get("answer_type", "unknown"),
            })

    print(f"Type mismatch samples: {len(type_mismatches)}\n")

    # Analyze: are these actually correct answers with wrong type?
    for i, m in enumerate(type_mismatches[:10]):
        print(f"=== Sample {i+1} ===")
        print(f"UID: {m['uid']}")
        print(f"Answer type annotation: {m['answer_type']}")
        print(f"Question: {m['question'][:150]}")
        print(f"Program: {m['program']}")
        print(f"Gold: {m['gold']} (type={m['gold_type']})")
        print(f"Pred: {m['pred']} (type={m['pred_type']})")

        # Check if numeric values match
        try:
            if m['gold_type'] == 'str' and m['pred_type'] in ('int', 'float'):
                gold_num = float(m['gold'])
                pred_num = float(m['pred'])
                if abs(gold_num - pred_num) < 0.001:
                    print(f"  → NUMERIC MATCH (evaluator type strictness issue)")
                else:
                    print(f"  → Numeric values differ: {gold_num} vs {pred_num}")
        except:
            pass

        # Check normalized string match
        norm_gold = normalize_answer(m['gold'])
        norm_pred = normalize_answer(m['pred'])
        if norm_gold == norm_pred:
            print(f"  → STRING NORMALIZED MATCH (evaluator bug)")

        print()

    # Summary: what fraction of failures are evaluator issues vs real errors?
    evaluator_bugs = 0
    real_errors = 0

    for m in type_mismatches:
        try:
            if m['gold_type'] == 'str' and m['pred_type'] in ('int', 'float'):
                gold_num = float(m['gold'])
                pred_num = float(m['pred'])
                if abs(gold_num - pred_num) < 0.001:
                    evaluator_bugs += 1
                    continue
        except:
            pass

        norm_gold = normalize_answer(m['gold'])
        norm_pred = normalize_answer(m['pred'])
        if norm_gold == norm_pred:
            evaluator_bugs += 1
        else:
            real_errors += 1

    print(f"\n=== Type Mismatch Attribution ===")
    print(f"Evaluator strictness (correct answer, wrong type): {evaluator_bugs}")
    print(f"Real errors: {real_errors}")
    print(f"Total type mismatches: {len(type_mismatches)}")

    if evaluator_bugs > 0:
        potential_gain = evaluator_bugs / 60  # 60 samples total
        print(f"\nPotential EM gain if evaluator fixed: +{potential_gain:.3f}")
        print(f"(from 0.117 → {0.117 + potential_gain:.3f})")


if __name__ == "__main__":
    main()
