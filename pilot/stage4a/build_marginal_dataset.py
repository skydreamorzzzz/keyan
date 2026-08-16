"""Build Stage 4A marginal-utility targets from rn1/rn2/rn3.

Features are inference-time safe. Labels are repeated-run marginal utility
targets relative to the default Both arm.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from executor import exec_program_re, match_result  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STAGE3 = os.path.join(ROOT, "pilot", "stage3")
OUT = os.path.dirname(__file__)
REPLICATES = ["rn1", "rn2", "rn3"]
ARMS = ["none", "case", "strategy", "both"]
ARM_TO_STAGE2 = {
    "none": "baseline",
    "case": "baseline_case",
    "strategy": "baseline_strategy",
    "both": "baseline_both",
}
DEVIATIONS = ["none", "case", "strategy"]


def load_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def annual_report_group(sample_id: str, filename: str | None = None) -> str:
    text = filename or sample_id
    parts = str(text).split("/")
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return str(text).split("/page_")[0]


def page_group(sample_id: str, filename: str | None = None) -> str:
    text = filename or sample_id
    if ".pdf" in str(text):
        return str(text).split(".pdf")[0] + ".pdf"
    return str(text).rsplit("-", 1)[0]


def safe_features(features: dict[str, Any]) -> dict[str, float]:
    out = {}
    banned = re.compile(r"gold|oracle|correct|preferred|label", re.I)
    for k, v in features.items():
        if banned.search(k):
            continue
        if isinstance(v, bool):
            v = int(v)
        if isinstance(v, (int, float)):
            out[k] = float(v)
    return out


def load_correctness() -> dict[int, dict[str, dict[str, bool]]]:
    dev = load_json(os.path.join(ROOT, "data", "finqa", "dev.json"))[:492]
    sample_indices = load_json(os.path.join(STAGE3, "stability", "sample_indices.json"))["indices"]
    per: dict[int, dict[str, dict[str, bool]]] = {i: {} for i in sample_indices}
    for rep in REPLICATES:
        run = load_json(os.path.join(STAGE3, "stability", f"stability_run_{rep}.json"))
        for i in sample_indices:
            per[i][rep] = {}
            for logical, arm in ARM_TO_STAGE2.items():
                raw = run["prog"][arm][str(i)]
                ok, res = exec_program_re(raw, dev[i]["table"])
                per[i][rep][logical] = bool(ok and match_result(res, dev[i]["qa"]["exe_ans"]))
    return per


def build() -> list[dict[str, Any]]:
    oracle = {r["sample_index"]: r for r in (json.loads(line) for line in open(os.path.join(STAGE3, "oracle_analysis_dataset.jsonl")))}
    corr = load_correctness()
    records = []
    for i in sorted(corr):
        base = oracle[i]
        rep_corr = corr[i]
        p_arm = {arm: sum(rep_corr[r][arm] for r in REPLICATES) / len(REPLICATES) for arm in ARMS}
        targets = {"p_correct": p_arm, "deviations": {}}
        for arm in DEVIATIONS:
            gain = sum(rep_corr[r][arm] and not rep_corr[r]["both"] for r in REPLICATES) / len(REPLICATES)
            harm = sum((not rep_corr[r][arm]) and rep_corr[r]["both"] for r in REPLICATES) / len(REPLICATES)
            delta = p_arm[arm] - p_arm["both"]
            targets["deviations"][arm] = {
                "delta": delta,
                "gain": gain,
                "harm": harm,
                "net_utility": gain - harm,
                "event_count": int(sum(rep_corr[r][arm] and not rep_corr[r]["both"] for r in REPLICATES)),
                "stable_2of3": int(sum(rep_corr[r][arm] and not rep_corr[r]["both"] for r in REPLICATES) >= 2),
                "stable_3of3": int(sum(rep_corr[r][arm] and not rep_corr[r]["both"] for r in REPLICATES) == 3),
            }
        rec = {
            "sample_index": i,
            "sample_id": base["sample_id"],
            "filename": base.get("filename"),
            "annual_report_group": annual_report_group(base["sample_id"], base.get("filename")),
            "page_group": page_group(base["sample_id"], base.get("filename")),
            "question": base["question"],
            "features": safe_features(base["features"]),
            "targets": targets,
            "replicate_correctness": rep_corr,
            "retrieval_sanitized": {
                "case": [
                    {k: r.get(k) for k in ["rank", "case_id", "score", "problem_kind", "n_steps", "struct", "operation_family", "question", "exe_ans"]}
                    for r in base["retrieval"]["case"]
                ],
                "strategy": [
                    {k: r.get(k) for k in ["rank", "strategy_id", "score", "case_hits", "name", "problem_pattern", "canonical_output_scale", "program_family"]}
                    for r in base["retrieval"]["strategy"]
                ],
            },
            "analysis_attribution_only": base.get("analysis", {}),
        }
        records.append(rec)
    os.makedirs(OUT, exist_ok=True)
    json.dump(records, open(os.path.join(OUT, "marginal_utility_dataset.json"), "w"), indent=2, ensure_ascii=False)
    with open(os.path.join(OUT, "marginal_utility_dataset.jsonl"), "w") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"saved {len(records)} records to {OUT}")
    return records


if __name__ == "__main__":
    build()
