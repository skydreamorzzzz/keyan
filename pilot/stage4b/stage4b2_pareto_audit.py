"""Stage 4B.2 sample-SE sensitivity, router stability, and Pareto audit."""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from statistics import mean

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stage2_official"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stage3"))

from run_development_nested import inner_candidates  # noqa: E402
from stage4b_common import ARMS, OUT, conservative_select, estimate_tokens, load_json, load_stage4a_records, load_stage4a_synthetic  # noqa: E402
from stability_run import build_prep, prompt_for  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def token_table() -> tuple[dict[int, dict[str, dict[str, float]]], list[int]]:
    dev = load_json(os.path.join(ROOT, "data", "finqa", "dev.json"))[:492]
    idxs = load_json(os.path.join(ROOT, "pilot", "stage3", "stability", "sample_indices.json"))["indices"]
    prep = build_prep(dev, idxs)
    table: dict[int, dict[str, dict[str, float]]] = {}
    for i in idxs:
        no_prompt, _ = prompt_for(prep[i], "none")
        no_tokens = estimate_tokens(no_prompt)
        table[i] = {}
        for arm in ARMS:
            prompt, _ = prompt_for(prep[i], arm)
            prompt_tokens = estimate_tokens(prompt)
            table[i][arm] = {
                "prompt_tokens": float(prompt_tokens),
                "memory_tokens": float(max(0, prompt_tokens - no_tokens)),
            }
    return table, idxs


def policy_cost(records, choices_by_sample, table, label):
    accs, prompt_tokens, memory_tokens = [], [], []
    by_sample = {r["sample_index"]: r for r in records}
    for sample_index, action in choices_by_sample.items():
        rec = by_sample[sample_index]
        accs.append(float(rec["targets"]["p_correct"][action]))
        prompt_tokens.append(table[sample_index][action]["prompt_tokens"])
        memory_tokens.append(table[sample_index][action]["memory_tokens"])
    return {
        "policy": label,
        "expected_accuracy": float(mean(accs)),
        "avg_prompt_tokens": float(mean(prompt_tokens)),
        "avg_memory_tokens": float(mean(memory_tokens)),
    }


def pareto(records, nested, table, idxs):
    out = []
    for arm in ARMS:
        out.append(policy_cost(records, {i: arm for i in idxs}, table, f"always_{arm}"))
    choices = {x["sample_index"]: x["choice"] for x in nested["choices"]}
    out.append(policy_cost(records, choices, table, "sample_se_nested_oof_policy"))
    return out


def deviation_savings(records, nested, table):
    by_sample = {r["sample_index"]: r for r in records}
    buckets = {
        "beneficial": [],
        "neutral": [],
        "harmful": [],
    }
    rows = []
    for choice in nested["choices"]:
        sample_index = choice["sample_index"]
        action = choice["choice"]
        if action == "both":
            continue
        delta = float(by_sample[sample_index]["targets"]["deviations"][action]["delta"])
        if delta > 0:
            bucket = "beneficial"
        elif delta < 0:
            bucket = "harmful"
        else:
            bucket = "neutral"
        prompt_saving = table[sample_index]["both"]["prompt_tokens"] - table[sample_index][action]["prompt_tokens"]
        memory_saving = table[sample_index]["both"]["memory_tokens"] - table[sample_index][action]["memory_tokens"]
        row = {
            "sample_index": sample_index,
            "action": action,
            "delta": delta,
            "bucket": bucket,
            "prompt_token_saving_vs_both": prompt_saving,
            "memory_token_saving_vs_both": memory_saving,
        }
        buckets[bucket].append(row)
        rows.append(row)

    summary = {}
    for bucket, vals in buckets.items():
        summary[bucket] = {
            "count": len(vals),
            "avg_prompt_token_saving_vs_both": float(mean([v["prompt_token_saving_vs_both"] for v in vals])) if vals else 0.0,
            "avg_memory_token_saving_vs_both": float(mean([v["memory_token_saving_vs_both"] for v in vals])) if vals else 0.0,
            "actions": dict(Counter(v["action"] for v in vals)),
        }
    return {"summary": summary, "rows": rows}


def fold_stability(nested):
    rows = [f["selected"] for f in nested["fold_selections"]]
    return {
        "fold_count": len(rows),
        "architecture_counts": dict(Counter(r["architecture"] for r in rows)),
        "feature_set_counts": dict(Counter(r["feature_set"] for r in rows)),
        "threshold_counts": dict(Counter(str(r["threshold"]) for r in rows)),
        "coverage_values": [float(r["coverage"]) for r in rows],
        "avg_inner_coverage": float(mean(float(r["coverage"]) for r in rows)),
        "selected_rows": rows,
    }


def select_deployable_candidate(records):
    synthetic = load_stage4a_synthetic()
    groups = [r["annual_report_group"] for r in records]
    idx = np.arange(len(records))
    cands = inner_candidates(records, synthetic, idx, groups)
    selected = conservative_select(cands, one_se=True)
    return {k: v for k, v in selected.items() if k not in {"fold_utils", "fold_gains"}}


def write_freeze(selected, audit):
    config = {
        "stage": "4B.2",
        "router_name": "stage4b2_sample_se_deployable_candidate",
        "frozen_at": "2026-08-16",
        "status": "candidate_freeze_not_confirmatory",
        "selection_data": "all 250-query development subset only",
        "selection_procedure": "same conservative inner GroupKFold procedure with sample-SE paired gain and explicit Always Both candidate",
        "selected_candidate": selected,
        "important_note": "Development performance is not confirmatory evidence; this candidate must be evaluated on a fresh holdout before method claims.",
    }
    path = os.path.join(OUT, "stage4b2_deployable_candidate_config.json")
    with open(path, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    spec = f"""# Stage 4B.2 Deployable Candidate Freeze

Router: `stage4b2_sample_se_deployable_candidate`

Status: candidate freeze only, not confirmatory evidence.

Selection data: the existing 250-query development subset.

Selection procedure:

- annual-report grouped inner CV on all development data
- paired gain over Always Both
- sample standard error (`ddof=1`)
- explicit Always Both candidate
- conservative one-SE tie-breaking
- original Stage 4B feature sets, architectures, thresholds, and lambdas only

Selected candidate:

```json
{json.dumps(selected, indent=2)}
```

Current sample-SE nested OOF performance:

- expected gain vs Both: {audit["nested_expected"]["gain_vs_both"]:.6f}
- deviation coverage: {audit["nested_expected"]["deviation_coverage"]:.3f}
- cluster CI: {audit["nested_expected"]["cluster_bootstrap"]["ci95"]}

This candidate must not be modified based on future holdout results.
"""
    with open(os.path.join(OUT, "STAGE4B2_DEPLOYABLE_CANDIDATE_SPEC.md"), "w") as f:
        f.write(spec)
    return config


def mark_old_freeze_superseded():
    path = os.path.join(OUT, "stage4b_frozen_router_config.json")
    cfg = load_json(path)
    cfg["superseded_by"] = "Stage 4B.1/4B.2 protocol repair"
    cfg["superseded_reason"] = (
        "Stage 4B.1 repaired paired-gain selection and realized-gain accounting; "
        "Stage 4B.2 uses sample-SE sensitivity. The old Always Both freeze is retained as historical artifact only."
    )
    cfg["historical_status"] = "superseded"
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def run():
    records = load_stage4a_records()
    nested = load_json(os.path.join(OUT, "development_nested_results.json"))
    stage4b1 = load_json(os.path.join(OUT, "stage4b1_reaudit_summary.json"))
    table, idxs = token_table()
    selected = select_deployable_candidate(records)
    audit = {
        "stage": "4B.2",
        "se_change": "sample std ddof=1",
        "stage4b1_population_se_nested": stage4b1["nested"]["expected_evaluation"],
        "sample_se_nested_expected": nested["expected_evaluation"],
        "sample_se_realized_by_replicate": nested["realized_by_replicate"],
        "fold_stability": fold_stability(nested),
        "pareto": pareto(records, nested, table, idxs),
        "deviation_savings": deviation_savings(records, nested, table),
        "deployable_candidate": selected,
        "final_judgment": "SIGNAL DISAPPEARS UNDER SAMPLE-SE",
    }
    audit["nested_expected"] = audit["sample_se_nested_expected"]
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "stage4b2_pareto_audit.json"), "w") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)
    config = write_freeze(selected, audit)
    audit["deployable_candidate_config_path"] = "pilot/stage4b/stage4b2_deployable_candidate_config.json"
    audit["deployable_candidate_config"] = config
    mark_old_freeze_superseded()
    with open(os.path.join(OUT, "stage4b2_pareto_audit.json"), "w") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)
    print(json.dumps({
        "sample_se_nested": nested["expected_evaluation"],
        "fold_stability": audit["fold_stability"],
        "deployable_candidate": selected,
        "final_judgment": audit["final_judgment"],
    }, indent=2))
    return audit


if __name__ == "__main__":
    run()
