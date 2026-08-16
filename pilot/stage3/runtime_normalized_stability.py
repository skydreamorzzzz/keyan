"""Runtime-normalized stability audit with held-out transfer bootstrap."""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from itertools import combinations
from statistics import mean
from typing import Any

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from executor import exec_program_re, match_result  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "stability")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ARMS = ["none", "case", "strategy", "both"]
ARM_TO_STAGE2 = {
    "none": "baseline",
    "case": "baseline_case",
    "strategy": "baseline_strategy",
    "both": "baseline_both",
}
BOOTSTRAP_SEED = 20260816
BOOTSTRAP_B = 10000


def load_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def sample_indices() -> list[int]:
    return load_json(os.path.join(OUT, "sample_indices.json"))["indices"]


def runtime_summary(name: str) -> dict[str, Any]:
    if name == "stage2_old":
        return {
            "replicate": name,
            "artifact_runtime_provenance": "insufficient",
            "requested_model": "DeepSeek-V4-flash[1m]",
            "backend": "anthropic_compatible",
            "effective_model": None,
            "model_version": None,
            "thinking_mode": False,
            "notes": "Historical arm_outputs.json stores outputs only, not response model/version/fingerprint.",
        }
    path = os.path.join(OUT, f"stability_run_{name}.json")
    if not os.path.exists(path):
        return {"replicate": name, "artifact_runtime_provenance": "missing"}
    data = load_json(path)
    runtimes = list((data.get("runtime_by_call") or {}).values())
    if not runtimes:
        return {
            "replicate": name,
            "artifact_runtime_provenance": "insufficient",
            "runtime_request": data.get("runtime_request"),
            "notes": "No per-call response runtime metadata was saved.",
        }
    keys = [
        "provider",
        "backend",
        "base_url",
        "endpoint",
        "requested_model",
        "effective_model",
        "response_model",
        "model_version",
        "system_fingerprint",
        "thinking_mode",
        "temperature",
        "max_tokens",
    ]
    values = {k: sorted({json.dumps(r.get(k), sort_keys=True) for r in runtimes}) for k in keys}
    return {
        "replicate": name,
        "artifact_runtime_provenance": "response_metadata_saved",
        "n_calls_with_runtime": len(runtimes),
        "unique_values": {k: [json.loads(v) for v in vals] for k, vals in values.items()},
        "runtime_request": data.get("runtime_request"),
        "retrieval_config": data.get("retrieval_config"),
        "memory_config": data.get("memory_config"),
        "prompt_config": data.get("prompt_config"),
    }


def load_replicates(names: list[str]) -> dict[str, dict[int, dict[str, bool]]]:
    dev = load_json(os.path.join(ROOT, "data", "finqa", "dev.json"))[:492]
    idxs = sample_indices()
    reps = {}
    for name in names:
        if name == "stage2_old":
            prog = load_json(os.path.join(ROOT, "pilot", "stage2_official", "output", "arm_outputs.json"))["prog"]
        else:
            path = os.path.join(OUT, f"stability_run_{name}.json")
            if not os.path.exists(path):
                continue
            prog = load_json(path)["prog"]
        per = {}
        complete = True
        for i in idxs:
            corr = {}
            for logical, arm in ARM_TO_STAGE2.items():
                if str(i) not in prog.get(arm, {}):
                    complete = False
                    break
                ok, res = exec_program_re(prog[arm][str(i)], dev[i]["table"])
                corr[logical] = bool(ok and match_result(res, dev[i]["qa"]["exe_ans"]))
            if not complete:
                break
            per[i] = corr
        if complete:
            reps[name] = per
    return reps


def fixed_oracle(per: dict[int, dict[str, bool]]) -> dict[str, Any]:
    n = len(per)
    acc = {a: sum(c[a] for c in per.values()) / n for a in ARMS}
    best_arm = max(ARMS, key=lambda a: acc[a])
    oracle = sum(any(c[a] for a in ARMS) for c in per.values()) / n
    return {
        "accuracy": acc,
        "best_fixed_arm": best_arm,
        "best_fixed": acc[best_arm],
        "oracle": oracle,
        "oracle_gap": oracle - acc[best_arm],
    }


def arm_agreement(reps: dict[str, dict[int, dict[str, bool]]]) -> dict[str, float]:
    names = list(reps)
    idxs = sorted(next(iter(reps.values())).keys())
    out = {}
    for arm in ARMS:
        vals = []
        for a, b in combinations(names, 2):
            vals.append(mean(reps[a][i][arm] == reps[b][i][arm] for i in idxs))
        out[arm] = float(mean(vals))
    return out


def event_stability(reps: dict[str, dict[int, dict[str, bool]]]) -> dict[str, Any]:
    names = list(reps)
    idxs = sorted(next(iter(reps.values())).keys())
    checks = {
        "case_gt_strategy": ("case", "strategy"),
        "strategy_gt_case": ("strategy", "case"),
        "case_gt_both": ("case", "both"),
        "strategy_gt_both": ("strategy", "both"),
    }
    out = {}
    for label, (a, b) in checks.items():
        any_count = ge2 = all3 = 0
        count_hist = Counter()
        for i in idxs:
            k = sum(reps[r][i][a] and not reps[r][i][b] for r in names)
            count_hist[k] += 1
            if k >= 1:
                any_count += 1
            if k >= 2:
                ge2 += 1
            if k == 3:
                all3 += 1
        out[label] = {
            "positive_any_run": any_count,
            "positive_in_at_least_2_runs": ge2,
            "positive_all_3_runs": all3,
            "at_least_2_rate_among_any": ge2 / any_count if any_count else 0.0,
            "all_3_rate_among_any": all3 / any_count if any_count else 0.0,
            "run_count_histogram": {str(k): int(v) for k, v in sorted(count_hist.items())},
        }
    return out


def expected_metrics(reps: dict[str, dict[int, dict[str, bool]]]) -> dict[str, Any]:
    names = list(reps)
    idxs = sorted(next(iter(reps.values())).keys())
    p = {i: {arm: mean(reps[r][i][arm] for r in names) for arm in ARMS} for i in idxs}
    arm_expected = {arm: mean(p[i][arm] for i in idxs) for arm in ARMS}
    expected_best = max(arm_expected.values())
    expected_oracle = mean(max(p[i][arm] for arm in ARMS) for i in idxs)
    return {
        "expected_arm_accuracy": arm_expected,
        "expected_best_fixed_arm": max(ARMS, key=lambda a: arm_expected[a]),
        "expected_best_fixed": expected_best,
        "expected_oracle": expected_oracle,
        "expected_oracle_gap": expected_oracle - expected_best,
        "one_shot_by_replicate": {name: fixed_oracle(per) for name, per in reps.items()},
    }


def bootstrap_ci(diff: np.ndarray, b: int = BOOTSTRAP_B, seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    n = len(diff)
    draws = rng.choice(n, size=(b, n), replace=True)
    vals = diff[draws].mean(axis=1)
    return {
        "point_estimate": float(diff.mean()),
        "ci95": [float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975))],
        "bootstrap_resamples": b,
        "random_seed": seed,
        "implementation": "paired percentile bootstrap over query-level differences: policy_correct_i - best_fixed_arm_correct_i",
    }


def heldout_transfer(reps: dict[str, dict[int, dict[str, bool]]]) -> dict[str, Any]:
    names = list(reps)
    idxs = sorted(next(iter(reps.values())).keys())
    folds = {}
    pooled_diff = []
    for heldout in names:
        train = [r for r in names if r != heldout]
        train_global = {arm: mean(reps[r][i][arm] for r in train for i in idxs) for arm in ARMS}
        choices = {}
        for i in idxs:
            scores = {arm: mean(reps[r][i][arm] for r in train) for arm in ARMS}
            choices[i] = max(ARMS, key=lambda arm: (scores[arm], train_global[arm]))

        fixed = {arm: mean(reps[heldout][i][arm] for i in idxs) for arm in ARMS}
        best_arm = max(ARMS, key=lambda a: fixed[a])
        policy_correct = np.array([int(reps[heldout][i][choices[i]]) for i in idxs], dtype=float)
        best_correct = np.array([int(reps[heldout][i][best_arm]) for i in idxs], dtype=float)
        oracle_correct = np.array([int(any(reps[heldout][i][a] for a in ARMS)) for i in idxs], dtype=float)
        diff = policy_correct - best_correct
        pooled_diff.extend(diff.tolist())
        oracle_gap = float(oracle_correct.mean() - best_correct.mean())
        folds[heldout] = {
            "train_runs": train,
            "train_global": train_global,
            "choice_distribution": dict(Counter(choices.values())),
            "policy_accuracy": float(policy_correct.mean()),
            "best_fixed_arm": best_arm,
            "best_fixed": float(best_correct.mean()),
            "oracle": float(oracle_correct.mean()),
            "oracle_gap": oracle_gap,
            "gain_over_best_fixed": float(diff.mean()),
            "oracle_gap_recovered": float(diff.mean() / oracle_gap) if oracle_gap > 0 else 0.0,
            "paired_bootstrap": bootstrap_ci(diff),
        }
    pooled_diff = np.array(pooled_diff, dtype=float)
    return {
        "folds": folds,
        "mean_policy_accuracy": float(mean(f["policy_accuracy"] for f in folds.values())),
        "mean_best_fixed": float(mean(f["best_fixed"] for f in folds.values())),
        "mean_oracle": float(mean(f["oracle"] for f in folds.values())),
        "mean_gain_over_best_fixed": float(mean(f["gain_over_best_fixed"] for f in folds.values())),
        "pooled_paired_bootstrap": bootstrap_ci(pooled_diff),
        "pooled_note": "Pooled over held-out run/query observations; query reuse across runs means fold-level CIs are primary.",
    }


def analyze(names: list[str], output: str) -> dict[str, Any]:
    reps = load_replicates(names)
    if set(names) != set(reps):
        raise RuntimeError(f"Incomplete replicates. requested={names} loaded={list(reps)}")
    out = {
        "replicates": names,
        "n": len(next(iter(reps.values()))),
        "runtime_identity": {name: runtime_summary(name) for name in names},
        "arm_agreement": arm_agreement(reps),
        "preference_event_stability": event_stability(reps),
        "expected": expected_metrics(reps),
        "heldout_preference_transfer": heldout_transfer(reps),
    }
    path = os.path.join(OUT, output)
    json.dump(out, open(path, "w"), indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"saved {path}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--replicates", nargs="+", default=["rn1", "rn2", "rn3"])
    ap.add_argument("--output", default="runtime_normalized_stability_analysis.json")
    args = ap.parse_args()
    analyze(args.replicates, args.output)
