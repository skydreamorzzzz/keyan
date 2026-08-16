"""Analysis tables for Stage 3.1 alignment features."""
from __future__ import annotations

import json
import os
from collections import defaultdict
from statistics import mean
from typing import Any

OUT = os.path.dirname(__file__)
ARMS = ["none", "case", "strategy", "both"]


def load_records() -> list[dict[str, Any]]:
    return [json.loads(line) for line in open(os.path.join(OUT, "alignment_feature_dataset.jsonl"))]


def group_arm_utility(records: list[dict[str, Any]], group_fn, label_key: str) -> dict[str, Any]:
    groups = defaultdict(list)
    for r in records:
        groups[str(group_fn(r))].append(r)
    out = {}
    for k, rows in sorted(groups.items()):
        corr = [r["labels"][label_key] for r in rows]
        out[k] = {"n": len(rows)}
        for arm in ARMS:
            out[k][arm] = mean(c[arm] for c in corr)
        out[k]["oracle"] = mean(any(c[a] for a in ARMS) for c in corr)
    return out


def summarize(label_key: str = "full_doc_prog_correct", suffix: str = "") -> dict[str, Any]:
    records = load_records()
    summary = {
        "label_key": label_key,
        "alignment_bucket_utility": group_arm_utility(
            records,
            lambda r: "high" if r["stage3_1"]["proxy"]["retrieval_alignment_high_conf"] else ("low" if r["stage3_1"]["proxy"]["retrieval_alignment_low_conf"] else "mid"),
            label_key,
        ),
        "case_predicted_family_agreement_utility": group_arm_utility(
            records, lambda r: r["stage3_1"]["proxy"]["case_predicted_family_agreement"], label_key
        ),
        "strategy_predicted_family_agreement_utility": group_arm_utility(
            records, lambda r: r["stage3_1"]["proxy"]["strategy_predicted_family_agreement"], label_key
        ),
        "scale_pollution_risk_utility": group_arm_utility(
            records,
            lambda r: bool(r["features_stage3_1"].get("scale_pollution_risk_case_fraction_for_percent_query", 0.0)),
            label_key,
        ),
    }
    name = "stage3_1_alignment_analysis" + (f"_{suffix}" if suffix else "") + ".json"
    json.dump(summary, open(os.path.join(OUT, name), "w"), indent=2, ensure_ascii=False)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    summarize()
