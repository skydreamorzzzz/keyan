"""Oracle-gap attribution tables for Stage 3."""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from statistics import mean
from typing import Any

OUT = os.path.dirname(__file__)
ARMS = ["none", "case", "strategy", "both"]


def load_records() -> list[dict[str, Any]]:
    return [json.loads(line) for line in open(os.path.join(OUT, "oracle_analysis_dataset.jsonl"))]


def pct(x: float) -> str:
    return f"{100*x:.1f}%"


def group_stats(records: list[dict[str, Any]], key_fn, label_key: str) -> dict[str, dict[str, float]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        buckets[str(key_fn(r))].append(r)
    out = {}
    for k, rows in sorted(buckets.items()):
        corr = [r["labels"][label_key] for r in rows]
        out[k] = {"n": len(rows)}
        for a in ARMS:
            out[k][a] = mean(c[a] for c in corr)
        out[k]["oracle"] = mean(any(c[a] for a in ARMS) for c in corr)
    return out


def summarize(label_key: str = "full_doc_prog_correct", suffix: str = "") -> dict[str, Any]:
    records = load_records()
    n = len(records)
    correct = [r["labels"][label_key] for r in records]
    fixed = {a: mean(c[a] for c in correct) for a in ARMS}
    oracle = mean(any(c[a] for a in ARMS) for c in correct)

    patterns = Counter(tuple(a for a in ARMS if c[a]) or ("none_correct",) for c in correct)
    exact_only = {a + "_only": sum(c[a] and sum(c[x] for x in ARMS) == 1 for c in correct) for a in ARMS}
    multi = Counter(sum(c[a] for a in ARMS) for c in correct)

    both_negative = [
        r for r in records
        if not r["labels"][label_key]["both"] and (r["labels"][label_key]["case"] or r["labels"][label_key]["strategy"])
    ]
    case_beats_strategy = [r for r in records if r["labels"][label_key]["case"] and not r["labels"][label_key]["strategy"]]
    strategy_beats_case = [r for r in records if r["labels"][label_key]["strategy"] and not r["labels"][label_key]["case"]]

    def compact(rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {}
        return {
            "n": len(rows),
            "gold_problem_family": Counter(r["analysis"]["gold_problem_family"] for r in rows).most_common(),
            "gold_operation_family": Counter(r["analysis"]["gold_operation_family"] for r in rows).most_common(),
            "mean_gold_n_steps": mean(r["analysis"]["gold_n_steps"] for r in rows),
            "uses_const_rate": mean(bool(r["analysis"]["uses_const"]) for r in rows),
            "percent_question_rate": mean(r["analysis"]["unit_percent_scale"]["question_percent"] for r in rows),
            "case_top_score_mean": mean(r["retrieval"]["case_top_score"] for r in rows),
            "strategy_top_score_mean": mean(r["retrieval"]["strategy_top_score"] for r in rows),
            "case_any_same_gold_struct_rate": mean(r["analysis"]["case_family_consistency_gold"]["any_same_struct"] for r in rows),
            "strategy_any_gold_match_rate": mean(r["analysis"]["strategy_family_consistency_gold"]["any_matches"] for r in rows),
            "case_strategy_overlap_mean": mean(r["retrieval"]["case_strategy_struct_overlap"] for r in rows),
        }

    conf_bins = {}
    for source, arm in [("case", "case"), ("strategy", "strategy")]:
        vals = sorted(r["retrieval"][f"{source}_top_score"] for r in records)
        q1, q2 = vals[n // 3], vals[(2 * n) // 3]
        def b(r):
            v = r["retrieval"][f"{source}_top_score"]
            return "low" if v <= q1 else ("mid" if v <= q2 else "high")
        conf_bins[source] = group_stats(records, b, label_key)
        conf_bins[source + "_utility_by_bin"] = {
            k: {"n": v["n"], f"{arm}_acc": v[arm], "none_acc": v["none"], "delta_vs_none": v[arm] - v["none"]}
            for k, v in conf_bins[source].items()
        }

    summary = {
        "n": n,
        "label_key": label_key,
        "fixed_accuracy": fixed,
        "best_fixed_arm": max(fixed, key=fixed.get),
        "best_fixed_accuracy": max(fixed.values()),
        "oracle_accuracy": oracle,
        "oracle_gap": oracle - max(fixed.values()),
        "exact_only_counts": exact_only,
        "correct_arm_set_distribution": {" + ".join(k): v for k, v in patterns.most_common()},
        "num_correct_arms_distribution": dict(sorted(multi.items())),
        "both_negative_interference": compact(both_negative),
        "case_beats_strategy": compact(case_beats_strategy),
        "strategy_beats_case": compact(strategy_beats_case),
        "by_gold_problem_family": group_stats(records, lambda r: r["analysis"]["gold_problem_family"], label_key),
        "by_gold_operation_family": group_stats(records, lambda r: r["analysis"]["gold_operation_family"], label_key),
        "by_gold_n_steps": group_stats(records, lambda r: r["analysis"]["gold_n_steps"], label_key),
        "by_uses_const": group_stats(records, lambda r: r["analysis"]["uses_const"], label_key),
        "by_case_gold_family_hit": group_stats(records, lambda r: r["analysis"]["case_family_consistency_gold"]["any_same_struct"], label_key),
        "by_strategy_gold_family_hit": group_stats(records, lambda r: r["analysis"]["strategy_family_consistency_gold"]["any_matches"], label_key),
        "retrieval_confidence_bins": conf_bins,
    }
    name = "oracle_gap_attribution" + (f"_{suffix}" if suffix else "") + ".json"
    json.dump(summary, open(os.path.join(OUT, name), "w"), indent=2, ensure_ascii=False)
    print(json.dumps(summary, indent=2, ensure_ascii=False)[:6000])
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label-key", default="full_doc_prog_correct")
    ap.add_argument("--suffix", default="")
    args = ap.parse_args()
    summarize(args.label_key, args.suffix)
