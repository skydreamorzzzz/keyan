"""Exact train-question duplicate robustness for Stage 3 strict labels."""
from __future__ import annotations

import json
import os
import re
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.dirname(__file__)
ARMS = ["none", "case", "strategy", "both"]


def norm_q(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip().lower())


def load_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def summarize(records: list[dict[str, Any]], label_key: str = "full_doc_prog_correct") -> dict[str, Any]:
    n = len(records)
    acc = {a: sum(r["labels"][label_key][a] for r in records) / n for a in ARMS}
    best = max(acc.values())
    oracle = sum(any(r["labels"][label_key][a] for a in ARMS) for r in records) / n
    return {
        "n": n,
        "accuracy": acc,
        "best_fixed_arm": max(acc, key=acc.get),
        "best_fixed": best,
        "oracle": oracle,
        "oracle_gap": oracle - best,
        "case_gain_vs_none": acc["case"] - acc["none"],
        "strategy_gain_vs_none": acc["strategy"] - acc["none"],
        "case_beats_strategy": sum(r["labels"][label_key]["case"] and not r["labels"][label_key]["strategy"] for r in records),
        "strategy_beats_case": sum(r["labels"][label_key]["strategy"] and not r["labels"][label_key]["case"] for r in records),
        "both_wrong_single_correct": sum((not r["labels"][label_key]["both"]) and (r["labels"][label_key]["case"] or r["labels"][label_key]["strategy"]) for r in records),
    }


def main() -> None:
    train = load_json(os.path.join(ROOT, "data", "finqa", "train.json"))
    train_questions = {norm_q(x["qa"]["question"]) for x in train}
    records = [json.loads(line) for line in open(os.path.join(OUT, "oracle_analysis_dataset.jsonl"))]
    dups = [r for r in records if norm_q(r["question"]) in train_questions]
    nondups = [r for r in records if norm_q(r["question"]) not in train_questions]
    out = {
        "definition": "lowercase whitespace-normalized exact match between official dev[:492] question and any train question",
        "duplicates_n": len(dups),
        "duplicate_sample_indices": [r["sample_index"] for r in dups],
        "all": summarize(records),
        "duplicates_only": summarize(dups) if dups else None,
        "duplicates_removed": summarize(nondups),
    }
    path = os.path.join(OUT, "duplicate_audit.json")
    json.dump(out, open(path, "w"), indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"saved {path}")


if __name__ == "__main__":
    main()
