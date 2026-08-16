"""Analyze repeated-run marginal utility stability."""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from itertools import combinations
from statistics import mean
from typing import Any

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


def load_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def sample_indices() -> list[int]:
    return load_json(os.path.join(OUT, "sample_indices.json"))["indices"]


def load_replicates(names: list[str]) -> dict[str, dict[int, dict[str, bool]]]:
    dev = load_json(os.path.join(ROOT, "data", "finqa", "dev.json"))[:492]
    idxs = sample_indices()
    reps = {}
    for name in names:
        if name == "stage2_old":
            outs = load_json(os.path.join(ROOT, "pilot", "stage2_official", "output", "arm_outputs.json"))
            prog = outs["prog"]
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
                raw = prog[arm][str(i)]
                ok, res = exec_program_re(raw, dev[i]["table"])
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
    best = max(acc.values())
    oracle = sum(any(c[a] for a in ARMS) for c in per.values()) / n
    return {
        "accuracy": acc,
        "best_fixed_arm": max(acc, key=acc.get),
        "best_fixed": best,
        "oracle": oracle,
        "oracle_gap": oracle - best,
    }


def agreement(reps: dict[str, dict[int, dict[str, bool]]]) -> dict[str, Any]:
    names = list(reps)
    idxs = sorted(next(iter(reps.values())).keys())
    out = {}
    for arm in ARMS:
        vals = []
        for a, b in combinations(names, 2):
            vals.append(mean(reps[a][i][arm] == reps[b][i][arm] for i in idxs))
        out[arm] = mean(vals) if vals else None
    return out


def sign(c: dict[str, bool], a: str, b: str) -> int:
    return int(c[a]) - int(c[b])


def sign_stability(reps: dict[str, dict[int, dict[str, bool]]]) -> dict[str, Any]:
    names = list(reps)
    idxs = sorted(next(iter(reps.values())).keys())
    checks = {
        "case_gt_strategy": ("case", "strategy"),
        "strategy_gt_case": ("strategy", "case"),
        "case_gt_both_negative_interference": ("case", "both"),
        "strategy_gt_both_negative_interference": ("strategy", "both"),
    }
    out = {}
    for name, (a, b) in checks.items():
        stable_positive = 0
        positive_any = 0
        positive_all = 0
        for i in idxs:
            signs = [sign(reps[r][i], a, b) for r in names]
            if any(s > 0 for s in signs):
                positive_any += 1
                if sum(s > 0 for s in signs) >= 2:
                    stable_positive += 1
                if all(s > 0 for s in signs):
                    positive_all += 1
        out[name] = {
            "positive_any_run": positive_any,
            "positive_in_at_least_2_runs": stable_positive,
            "positive_all_runs": positive_all,
            "stability_among_positive_any": stable_positive / positive_any if positive_any else 0.0,
        }
    return out


def expected_metrics(reps: dict[str, dict[int, dict[str, bool]]]) -> dict[str, Any]:
    names = list(reps)
    idxs = sorted(next(iter(reps.values())).keys())
    p = {
        i: {arm: mean(reps[r][i][arm] for r in names) for arm in ARMS}
        for i in idxs
    }
    arm_expected = {arm: mean(p[i][arm] for i in idxs) for arm in ARMS}
    expected_best_fixed = max(arm_expected.values())
    expected_oracle = mean(max(p[i][arm] for arm in ARMS) for i in idxs)
    oneshot = {name: fixed_oracle(per) for name, per in reps.items()}
    return {
        "p_by_sample": p,
        "expected_arm_accuracy": arm_expected,
        "expected_best_fixed_arm": max(arm_expected, key=arm_expected.get),
        "expected_best_fixed": expected_best_fixed,
        "expected_oracle": expected_oracle,
        "expected_oracle_gap": expected_oracle - expected_best_fixed,
        "one_shot_by_replicate": oneshot,
    }


def cross_run_preference_transfer(reps: dict[str, dict[int, dict[str, bool]]]) -> dict[str, Any]:
    names = list(reps)
    idxs = sorted(next(iter(reps.values())).keys())
    folds = {}
    for heldout in names:
        train = [r for r in names if r != heldout]
        train_global = {arm: mean(reps[r][i][arm] for r in train for i in idxs) for arm in ARMS}
        train_best = max(train_global, key=train_global.get)
        choices = {}
        for i in idxs:
            scores = {arm: mean(reps[r][i][arm] for r in train) for arm in ARMS}
            choices[i] = max(ARMS, key=lambda arm: (scores[arm], train_global[arm]))
        selector_acc = mean(reps[heldout][i][choices[i]] for i in idxs)
        heldout_fixed = {arm: mean(reps[heldout][i][arm] for i in idxs) for arm in ARMS}
        folds[heldout] = {
            "train_best_fixed_arm": train_best,
            "choice_distribution": dict(Counter(choices.values())),
            "selector_accuracy_on_heldout": selector_acc,
            "heldout_best_fixed_arm": max(heldout_fixed, key=heldout_fixed.get),
            "heldout_best_fixed": max(heldout_fixed.values()),
            "delta_vs_heldout_best_fixed": selector_acc - max(heldout_fixed.values()),
            "heldout_fixed": heldout_fixed,
        }
    return {
        "folds": folds,
        "mean_selector_accuracy": mean(f["selector_accuracy_on_heldout"] for f in folds.values()),
        "mean_heldout_best_fixed": mean(f["heldout_best_fixed"] for f in folds.values()),
        "mean_delta_vs_heldout_best_fixed": mean(f["delta_vs_heldout_best_fixed"] for f in folds.values()),
    }


def analyze(names: list[str]) -> dict[str, Any]:
    reps = load_replicates(names)
    if len(reps) < 2:
        raise RuntimeError(f"Need at least 2 complete replicates, found {list(reps)}")
    out = {
        "replicates": list(reps),
        "n": len(next(iter(reps.values()))),
        "arm_agreement": agreement(reps),
        "sign_stability": sign_stability(reps),
        "expected": expected_metrics(reps),
        "cross_run_preference_transfer": cross_run_preference_transfer(reps),
    }
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "stability_analysis.json")
    json.dump(out, open(path, "w"), indent=2, ensure_ascii=False)
    compact = dict(out)
    compact["expected"] = {k: v for k, v in out["expected"].items() if k != "p_by_sample"}
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    print(f"saved {path}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--replicates", nargs="+", default=["stage2_old", "r1", "r2"])
    args = ap.parse_args()
    analyze(args.replicates)
