"""Fully nested annual-report grouped development audit for Stage 4B."""
from __future__ import annotations

import json
import os
from statistics import mean
from typing import Any

import numpy as np

from stage4b_common import (
    ARMS,
    DEVIATIONS,
    OUT,
    action_correct_expected,
    best_deviation_label,
    conservative_select,
    evaluate_expected,
    evaluate_realized_by_replicate,
    feature_dict,
    folds_for_groups,
    load_stage4a_records,
    load_stage4a_synthetic,
    logreg_model,
    p_correct,
    reg_model,
    vectorize_train_test,
)

FEATURE_SETS = [
    "existing_meta",
    "existing_meta_plus_compatibility",
    "synthetic_interaction",
    "existing_meta_plus_interaction",
]
ARCHITECTURES = ["flat_delta", "gain_harm", "hierarchical"]
THRESHOLDS = [0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.33, 0.5]
GATE_THRESHOLDS = [0.4, 0.5, 0.6, 0.7, 0.8]
LAMBDAS = [1.0, 1.5, 2.0, 3.0]


def se(vals: list[float]) -> float:
    return float(np.std(vals, ddof=1) / (len(vals) ** 0.5)) if len(vals) > 1 else 0.0


def fit_flat_delta(records, synthetic, feature_set, train_idx, test_idx):
    _, x_train, x_test = vectorize_train_test(records, synthetic, feature_set, train_idx, test_idx)
    preds = {}
    for arm in DEVIATIONS:
        y = np.array([records[i]["targets"]["deviations"][arm]["delta"] for i in train_idx])
        model = reg_model()
        model.fit(x_train, y)
        preds[arm] = model.predict(x_test)
    return preds


def choices_flat_delta(preds, test_idx, threshold):
    choices = {}
    for pos, idx in enumerate(test_idx):
        scores = {a: float(preds[a][pos]) for a in DEVIATIONS}
        best = max(DEVIATIONS, key=lambda a: scores[a])
        choices[int(idx)] = best if scores[best] > threshold else "both"
    return choices


def fit_gain_harm(records, synthetic, feature_set, train_idx, test_idx):
    _, x_train, x_test = vectorize_train_test(records, synthetic, feature_set, train_idx, test_idx)
    probs = {"gain": {}, "harm": {}}
    for arm in DEVIATIONS:
        for target in ["gain", "harm"]:
            y = np.array([int(records[i]["targets"]["deviations"][arm][target] > 0) for i in train_idx])
            if len(set(y)) < 2:
                probs[target][arm] = np.full(len(test_idx), float(np.mean(y)))
            else:
                model = logreg_model()
                model.fit(x_train, y)
                probs[target][arm] = model.predict_proba(x_test)[:, 1]
    return probs


def choices_gain_harm(probs, test_idx, threshold, lam):
    choices = {}
    for pos, idx in enumerate(test_idx):
        scores = {a: float(probs["gain"][a][pos] - lam * probs["harm"][a][pos]) for a in DEVIATIONS}
        best = max(DEVIATIONS, key=lambda a: scores[a])
        choices[int(idx)] = best if scores[best] > threshold else "both"
    return choices


def fit_hierarchical(records, synthetic, feature_set, train_idx, test_idx):
    _, x_train, x_test = vectorize_train_test(records, synthetic, feature_set, train_idx, test_idx)
    y_gate = np.array([int(max(records[i]["targets"]["deviations"][a]["delta"] for a in DEVIATIONS) > 0) for i in train_idx])
    if len(set(y_gate)) < 2:
        gate_prob = np.full(len(test_idx), float(np.mean(y_gate)))
    else:
        gate = logreg_model()
        gate.fit(x_train, y_gate)
        gate_prob = gate.predict_proba(x_test)[:, 1]

    pos_train = [i for i in train_idx if max(records[i]["targets"]["deviations"][a]["delta"] for a in DEVIATIONS) > 0]
    labels = [best_deviation_label(records[i]) for i in pos_train]
    if len(pos_train) < 6 or len(set(labels)) < 2:
        fallback = max(DEVIATIONS, key=lambda a: sum(records[i]["targets"]["deviations"][a]["delta"] for i in train_idx))
        arm_prob = {a: np.full(len(test_idx), 1.0 if a == fallback else 0.0) for a in DEVIATIONS}
    else:
        vec, x_pos, x_test2 = vectorize_train_test(records, synthetic, feature_set, pos_train, test_idx)
        clf = logreg_model()
        clf.fit(x_pos, labels)
        proba = clf.predict_proba(x_test2)
        arm_prob = {a: np.zeros(len(test_idx)) for a in DEVIATIONS}
        for j, cls in enumerate(clf.classes_):
            arm_prob[cls] = proba[:, j]
    return {"gate_prob": gate_prob, "arm_prob": arm_prob}


def choices_hierarchical(pred, test_idx, threshold, case_extra=0.15):
    choices = {}
    for pos, idx in enumerate(test_idx):
        if pred["gate_prob"][pos] <= threshold:
            choices[int(idx)] = "both"
            continue
        arm_scores = {a: float(pred["arm_prob"][a][pos]) for a in DEVIATIONS}
        best = max(DEVIATIONS, key=lambda a: arm_scores[a])
        if best == "case" and pred["gate_prob"][pos] <= min(0.95, threshold + case_extra):
            choices[int(idx)] = "both"
            continue
        choices[int(idx)] = best
    return choices


def eval_choices(records, choices: dict[int, str]) -> tuple[float, float, float]:
    idxs = sorted(choices)
    vals = [action_correct_expected(records, i, choices[i]) for i in idxs]
    both_vals = [p_correct(records, i, "both") for i in idxs]
    cov = [choices[i] != "both" for i in sorted(choices)]
    return float(mean(vals)), float(mean(vals) - mean(both_vals)), float(mean(cov))


def inner_candidates(records, synthetic, train_idx, groups) -> list[dict[str, Any]]:
    train_idx = np.array(train_idx)
    inner_groups = [groups[i] for i in train_idx]
    candidates: dict[tuple, dict[str, Any]] = {("always_both", "none", None, None): {"fold_utils": [], "fold_gains": [], "fold_covs": []}}
    for val_train_pos, val_pos in folds_for_groups(inner_groups, n_splits=3):
        inner_train = train_idx[val_train_pos]
        val = train_idx[val_pos]
        both_choices = {int(i): "both" for i in val}
        util, gain, cov = eval_choices(records, both_choices)
        candidates[("always_both", "none", None, None)]["fold_utils"].append(util)
        candidates[("always_both", "none", None, None)]["fold_gains"].append(gain)
        candidates[("always_both", "none", None, None)]["fold_covs"].append(cov)
        for fs in FEATURE_SETS:
            preds_flat = fit_flat_delta(records, synthetic, fs, inner_train, val)
            for t in THRESHOLDS:
                choices = choices_flat_delta(preds_flat, val, t)
                util, gain, cov = eval_choices(records, choices)
                key = ("flat_delta", fs, t, None)
                candidates.setdefault(key, {"fold_utils": [], "fold_gains": [], "fold_covs": []})
                candidates[key]["fold_utils"].append(util)
                candidates[key]["fold_gains"].append(gain)
                candidates[key]["fold_covs"].append(cov)

            probs = fit_gain_harm(records, synthetic, fs, inner_train, val)
            for lam in LAMBDAS:
                for t in THRESHOLDS:
                    choices = choices_gain_harm(probs, val, t, lam)
                    util, gain, cov = eval_choices(records, choices)
                    key = ("gain_harm", fs, t, lam)
                    candidates.setdefault(key, {"fold_utils": [], "fold_gains": [], "fold_covs": []})
                    candidates[key]["fold_utils"].append(util)
                    candidates[key]["fold_gains"].append(gain)
                    candidates[key]["fold_covs"].append(cov)

            pred_h = fit_hierarchical(records, synthetic, fs, inner_train, val)
            for t in GATE_THRESHOLDS:
                choices = choices_hierarchical(pred_h, val, t)
                util, gain, cov = eval_choices(records, choices)
                key = ("hierarchical", fs, t, None)
                candidates.setdefault(key, {"fold_utils": [], "fold_gains": [], "fold_covs": []})
                candidates[key]["fold_utils"].append(util)
                candidates[key]["fold_gains"].append(gain)
                candidates[key]["fold_covs"].append(cov)
    out = []
    for (arch, fs, t, lam), rec in candidates.items():
        out.append({
            "architecture": arch,
            "feature_set": fs,
            "threshold": t,
            "lambda": lam,
            "mean_utility": float(mean(rec["fold_utils"])),
            "se_utility": float(se(rec["fold_utils"])),
            "mean_gain": float(mean(rec["fold_gains"])),
            "se_gain": float(se(rec["fold_gains"])),
            "coverage": float(mean(rec["fold_covs"])),
            "fold_utils": rec["fold_utils"],
            "fold_gains": rec["fold_gains"],
        })
    return out


def fit_predict_selected(records, synthetic, selected, train_idx, test_idx):
    arch = selected["architecture"]
    fs = selected["feature_set"]
    if arch == "always_both":
        return {int(i): "both" for i in test_idx}
    if arch == "flat_delta":
        preds = fit_flat_delta(records, synthetic, fs, train_idx, test_idx)
        return choices_flat_delta(preds, test_idx, selected["threshold"])
    if arch == "gain_harm":
        probs = fit_gain_harm(records, synthetic, fs, train_idx, test_idx)
        return choices_gain_harm(probs, test_idx, selected["threshold"], selected["lambda"])
    if arch == "hierarchical":
        pred = fit_hierarchical(records, synthetic, fs, train_idx, test_idx)
        return choices_hierarchical(pred, test_idx, selected["threshold"])
    raise ValueError(arch)


def run() -> dict[str, Any]:
    records = load_stage4a_records()
    synthetic = load_stage4a_synthetic()
    groups = [r["annual_report_group"] for r in records]
    choices = ["both"] * len(records)
    fold_selections = []
    for fold_id, (train_idx, test_idx) in enumerate(folds_for_groups(groups, n_splits=5), 1):
        cands = inner_candidates(records, synthetic, train_idx, groups)
        selected = conservative_select(cands, one_se=True)
        pred = fit_predict_selected(records, synthetic, selected, np.array(train_idx), np.array(test_idx))
        for idx, action in pred.items():
            choices[idx] = action
        fold_selections.append({
            "fold": fold_id,
            "selected": {k: v for k, v in selected.items() if k != "fold_utils"},
            "test_n": len(test_idx),
            "test_groups": len({groups[i] for i in test_idx}),
        })
        print(f"fold {fold_id}: {fold_selections[-1]['selected']}")
    result = {
        "protocol": {
            "outer": "GroupKFold by annual_report_group",
            "inner": "GroupKFold on outer train only",
            "preprocessing": "DictVectorizer fit inside each train fold only",
            "selection": "one-standard-error conservative selection; tie prefers lower coverage/higher threshold/higher lambda",
            "selection_metric": "paired inner-CV gain over Always Both",
            "se_estimator": "sample standard error, numpy std(ddof=1) / sqrt(n)",
            "candidate_feature_sets": FEATURE_SETS,
            "candidate_architectures": ARCHITECTURES,
        },
        "fold_selections": fold_selections,
        "choices": [{"sample_index": r["sample_index"], "choice": choices[i], "annual_report_group": r["annual_report_group"]} for i, r in enumerate(records)],
        "expected_evaluation": evaluate_expected(records, choices, "annual_report_group"),
        "realized_by_replicate": evaluate_realized_by_replicate(records, choices),
    }
    os.makedirs(OUT, exist_ok=True)
    json.dump(result, open(os.path.join(OUT, "development_nested_results.json"), "w"), indent=2, ensure_ascii=False)
    print(json.dumps({k: result[k] for k in ["expected_evaluation", "realized_by_replicate"]}, indent=2))
    return result


if __name__ == "__main__":
    run()
