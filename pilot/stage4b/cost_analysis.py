"""Accuracy-memory cost analysis for Stage 4B policies."""
from __future__ import annotations

import json
import os
import sys
from statistics import mean

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stage2_official"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stage3"))

from stage4b_common import ARMS, OUT, estimate_tokens, load_json, load_stage4a_records  # noqa: E402
from stability_run import build_prep, deterministic_subset, prompt_for  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def dev_costs():
    dev = load_json(os.path.join(ROOT, "data", "finqa", "dev.json"))[:492]
    idxs = load_json(os.path.join(ROOT, "pilot", "stage3", "stability", "sample_indices.json"))["indices"]
    prep = build_prep(dev, idxs)
    records = load_stage4a_records()
    by_sample = {r["sample_index"]: r for r in records}
    rows = []
    for arm in ARMS:
        costs = []
        accs = []
        mems = []
        for i in idxs:
            prompt, _ = prompt_for(prep[i], arm)
            no_prompt, _ = prompt_for(prep[i], "none")
            total = estimate_tokens(prompt)
            mem = max(0, total - estimate_tokens(no_prompt))
            costs.append(total)
            mems.append(mem)
            accs.append(by_sample[i]["targets"]["p_correct"][arm])
        rows.append({
            "policy": f"always_{arm}",
            "expected_accuracy": float(mean(accs)),
            "avg_prompt_tokens": float(mean(costs)),
            "avg_memory_tokens": float(mean(mems)),
        })
    nested = load_json(os.path.join(OUT, "development_nested_results.json"))
    choices = {x["sample_index"]: x["choice"] for x in nested["choices"]}
    costs = []
    mems = []
    accs = []
    for i in idxs:
        arm = choices[i]
        prompt, _ = prompt_for(prep[i], arm)
        no_prompt, _ = prompt_for(prep[i], "none")
        total = estimate_tokens(prompt)
        mem = max(0, total - estimate_tokens(no_prompt))
        costs.append(total)
        mems.append(mem)
        accs.append(by_sample[i]["targets"]["p_correct"][arm])
    rows.append({
        "policy": "frozen_nested_router",
        "expected_accuracy": float(mean(accs)),
        "avg_prompt_tokens": float(mean(costs)),
        "avg_memory_tokens": float(mean(mems)),
    })
    return rows


def run():
    out = {
        "development_pareto": dev_costs(),
        "holdout_cost": load_json(os.path.join(OUT, "holdout_confirmation.json"))["token_cost"],
    }
    json.dump(out, open(os.path.join(OUT, "cost_analysis.json"), "w"), indent=2)
    print(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    run()
