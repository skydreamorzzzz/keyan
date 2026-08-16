"""Label/support audit for Stage 4A marginal utility targets."""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from statistics import mean
from typing import Any

OUT = os.path.dirname(__file__)
DEVIATIONS = ["none", "case", "strategy"]


def load_records() -> list[dict[str, Any]]:
    return [json.loads(line) for line in open(os.path.join(OUT, "marginal_utility_dataset.jsonl"))]


def query_family(rec: dict[str, Any]) -> str:
    f = rec["features"]
    if f.get("asks_change"):
        return "change"
    if f.get("asks_ratio") or f.get("asks_percent"):
        return "ratio_percent"
    if f.get("asks_sum"):
        return "aggregation"
    if f.get("asks_average"):
        return "average"
    if f.get("asks_compare"):
        return "comparison"
    return "other"


def audit() -> dict[str, Any]:
    records = load_records()
    out: dict[str, Any] = {
        "n": len(records),
        "annual_report_groups": len({r["annual_report_group"] for r in records}),
        "page_groups": len({r["page_group"] for r in records}),
        "deviation_support": {},
        "overlap": {},
        "gain_harm_distribution": {},
    }
    event_sets = {}
    for arm in DEVIATIONS:
        any_set = {r["sample_index"] for r in records if r["targets"]["deviations"][arm]["event_count"] >= 1}
        ge2_set = {r["sample_index"] for r in records if r["targets"]["deviations"][arm]["event_count"] >= 2}
        all3_set = {r["sample_index"] for r in records if r["targets"]["deviations"][arm]["event_count"] == 3}
        event_sets[arm] = any_set
        annual = Counter(r["annual_report_group"] for r in records if r["sample_index"] in any_set)
        family = Counter(query_family(r) for r in records if r["sample_index"] in any_set)
        gains = [r["targets"]["deviations"][arm]["gain"] for r in records]
        harms = [r["targets"]["deviations"][arm]["harm"] for r in records]
        deltas = [r["targets"]["deviations"][arm]["delta"] for r in records]
        out["deviation_support"][arm] = {
            "any_run": len(any_set),
            "stable_2of3": len(ge2_set),
            "stable_3of3": len(all3_set),
            "annual_reports_with_any": len(annual),
            "top_annual_reports": annual.most_common(10),
            "max_annual_report_share": (annual.most_common(1)[0][1] / len(any_set)) if any_set else 0.0,
            "family_distribution": dict(family),
        }
        out["gain_harm_distribution"][arm] = {
            "mean_gain": mean(gains),
            "mean_harm": mean(harms),
            "mean_delta": mean(deltas),
            "positive_delta_n": sum(x > 0 for x in deltas),
            "zero_delta_n": sum(x == 0 for x in deltas),
            "negative_delta_n": sum(x < 0 for x in deltas),
            "gain_hist": dict(Counter(str(x) for x in gains)),
            "harm_hist": dict(Counter(str(x) for x in harms)),
            "delta_hist": dict(Counter(str(x) for x in deltas)),
        }
    for a in DEVIATIONS:
        for b in DEVIATIONS:
            if a >= b:
                continue
            inter = event_sets[a] & event_sets[b]
            out["overlap"][f"{a}+{b}"] = {
                "any_overlap_n": len(inter),
                "jaccard": len(inter) / len(event_sets[a] | event_sets[b]) if (event_sets[a] | event_sets[b]) else 0.0,
            }
    by_report_events = defaultdict(int)
    for r in records:
        if any(r["targets"]["deviations"][a]["event_count"] >= 1 for a in DEVIATIONS):
            by_report_events[r["annual_report_group"]] += 1
    out["all_deviation_events"] = {
        "any_deviation_query_n": sum(any(r["targets"]["deviations"][a]["event_count"] >= 1 for a in DEVIATIONS) for r in records),
        "annual_reports_with_any_deviation": len(by_report_events),
        "top_annual_reports": Counter(by_report_events).most_common(10),
    }
    json.dump(out, open(os.path.join(OUT, "support_audit.json"), "w"), indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return out


if __name__ == "__main__":
    audit()
