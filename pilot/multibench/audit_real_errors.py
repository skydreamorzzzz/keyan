"""Analyze the 15 real errors: where did the model go wrong?

Categories:
1. Wrong operands extracted from tables
2. Wrong operation chosen
3. Scale/unit errors (0.16 vs 16.0, millions vs absolute)
4. Calculation errors
5. Evidence not found
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
    return {(r["uid"], r["arm"]): r for r in records}


def load_validation():
    tbl = pq.read_table(VAL_PATH)
    rows = []
    for i in range(tbl.num_rows):
        row = {col: tbl[col][i].as_py() for col in tbl.column_names}
        rows.append(row)
    return {row["uid"]: row for row in rows}


def classify_error(pred, gold, program, question):
    """Classify the error type."""
    # Scale error: off by factor of 100 or 1000
    try:
        pred_num = float(pred)
        gold_num = float(gold)
        ratio = pred_num / gold_num if gold_num != 0 else float('inf')

        if abs(ratio - 100) < 1 or abs(ratio - 0.01) < 0.001:
            return "scale_percent_error"
        if abs(ratio - 1000) < 10 or abs(ratio - 0.001) < 0.00001:
            return "scale_thousands_error"
        if abs(pred_num) < 0.01 and abs(gold_num) > 100:
            return "wrong_operands_zero_result"
        if abs(pred_num - gold_num) / max(abs(gold_num), abs(pred_num)) < 0.05:
            return "calculation_error_small"
    except:
        pass

    # List vs scalar confusion
    if isinstance(pred, list) and not isinstance(gold, list):
        return "returned_list_instead_of_sum"

    # Completely wrong value
    return "wrong_extraction_or_logic"


def main():
    cache = load_cache()
    val_data = load_validation()

    # Get none arm errors
    errors = []
    for uid in val_data:
        rec = cache.get((uid, "none"))
        if not rec:
            continue

        gold_row = val_data[uid]
        pred = rec.get("answer")
        gold = gold_row.get("answer")

        # Skip type-strictness matches
        try:
            if isinstance(gold, str) and isinstance(pred, (int, float)):
                if abs(float(gold) - float(pred)) < 0.001:
                    continue
        except:
            pass

        if str(pred).strip().lower() != str(gold).strip().lower():
            error_type = classify_error(pred, gold, gold_row.get("program", ""), gold_row.get("question", ""))
            errors.append({
                "uid": uid,
                "pred": pred,
                "gold": gold,
                "program": gold_row.get("program", ""),
                "question": gold_row.get("question", ""),
                "error_type": error_type,
            })

    # Count by type
    from collections import Counter
    type_counts = Counter(e["error_type"] for e in errors)

    print(f"=== Real Error Classification (n={len(errors)}) ===\n")
    for error_type, count in type_counts.most_common():
        print(f"{error_type}: {count}")

    # Show examples of each type
    print("\n=== Error Examples ===\n")
    seen_types = set()
    for e in errors[:30]:
        if e["error_type"] not in seen_types:
            seen_types.add(e["error_type"])
            print(f"[{e['error_type']}]")
            print(f"Q: {e['question'][:120]}")
            print(f"Program: {e['program']}")
            print(f"Gold: {e['gold']}")
            print(f"Pred: {e['pred']}")
            print()


if __name__ == "__main__":
    main()
