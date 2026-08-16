"""Stage 3.1 selector ablations over alignment features."""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, recall_score
from sklearn.model_selection import KFold, StratifiedKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

OUT = os.path.dirname(__file__)
ARMS = ["none", "case", "strategy", "both"]
MODES = [
    "previous_query_only",
    "previous_retrieval_metadata",
    "predicted_family",
    "operand_structure",
    "unit_scale",
    "semantic_consistency",
    "all_stage3_1",
    "previous_plus_all_stage3_1",
]


def load_records() -> list[dict[str, Any]]:
    return [json.loads(line) for line in open(os.path.join(OUT, "alignment_feature_dataset.jsonl"))]


def previous_subset(features: dict[str, Any], query_only: bool) -> dict[str, float]:
    out = {}
    for k, v in features.items():
        if isinstance(v, bool):
            v = int(v)
        if not isinstance(v, (int, float)):
            continue
        is_retrieval = k.startswith(("case_", "strategy_", "retrieval_", "both_"))
        is_repr = "_emb64_" in k
        if query_only and is_retrieval:
            continue
        if is_repr:
            continue
        out[k] = float(v)
    return out


def stage31_subset(features: dict[str, Any], group: str) -> dict[str, float]:
    prefixes = {
        "predicted_family": ("pred_family_", "case_pred_family_", "strategy_pred_family_", "case_strategy_pred_family", "case_top_pred_family_", "strategy_top_pred_family_"),
        "operand_structure": ("query_role_", "query_role_count", "case_role_", "strategy_role_", "case_year_", "case_symbolic_", "case_step_", "case_struct_", "strategy_struct_", "case_family_", "strategy_family_"),
        "unit_scale": ("query_scale_", "case_scale_", "strategy_scale_", "scale_pollution_", "case_strategy_scale_"),
        "semantic_consistency": ("case_score_x_", "strategy_score_x_", "case_top_conflict_", "strategy_top_conflict_", "retrieval_alignment_", "case_strategy_family_disagreement"),
    }
    if group == "all_stage3_1":
        return {k: float(v) for k, v in features.items() if isinstance(v, (int, float, bool))}
    keep = prefixes[group]
    return {k: float(v) for k, v in features.items() if k.startswith(keep) and isinstance(v, (int, float, bool))}


def feature_subset(rec: dict[str, Any], mode: str) -> dict[str, float]:
    if mode == "previous_query_only":
        return previous_subset(rec["features"], query_only=True)
    if mode == "previous_retrieval_metadata":
        return previous_subset(rec["features"], query_only=False)
    if mode in {"predicted_family", "operand_structure", "unit_scale", "semantic_consistency", "all_stage3_1"}:
        return stage31_subset(rec["features_stage3_1"], mode)
    if mode == "previous_plus_all_stage3_1":
        out = previous_subset(rec["features"], query_only=False)
        out.update(stage31_subset(rec["features_stage3_1"], "all_stage3_1"))
        return out
    raise ValueError(mode)


def preferred_label(correct: dict[str, bool], priors: dict[str, float]) -> str:
    ok = [a for a in ARMS if correct[a]]
    if not ok:
        return "none"
    return max(ok, key=lambda a: (priors[a], a == "both"))


def folds_for(y: list[str], n_splits: int = 5):
    counts = Counter(y)
    if min(counts.values()) >= n_splits:
        return StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=20260816).split(np.zeros(len(y)), y)
    return KFold(n_splits=n_splits, shuffle=True, random_state=20260816).split(np.zeros(len(y)))


def fresh_model(name: str):
    if name == "logreg":
        return make_pipeline(StandardScaler(with_mean=False), LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5))
    if name == "tree":
        return DecisionTreeClassifier(max_depth=4, min_samples_leaf=12, class_weight="balanced", random_state=20260816)
    if name == "rf":
        return RandomForestClassifier(n_estimators=300, max_depth=5, min_samples_leaf=8, class_weight="balanced", random_state=20260816)
    if name == "mlp":
        return make_pipeline(StandardScaler(with_mean=False), MLPClassifier(hidden_layer_sizes=(32,), alpha=0.01, max_iter=600, random_state=20260816))
    raise ValueError(name)


def evaluate(records: list[dict[str, Any]], choices: list[str], label_key: str, preferred: list[str]) -> dict[str, Any]:
    correct = [r["labels"][label_key] for r in records]
    acc = float(np.mean([correct[i][choices[i]] for i in range(len(records))]))
    fixed = {a: float(np.mean([c[a] for c in correct])) for a in ARMS}
    best_fixed = max(fixed.values())
    oracle = float(np.mean([any(c[a] for a in ARMS) for c in correct]))
    avoidable = [i for i, c in enumerate(correct) if not c["both"] and (c["case"] or c["strategy"])]
    strategy_beats = [i for i, c in enumerate(correct) if c["strategy"] and not c["case"]]
    case_beats = [i for i, c in enumerate(correct) if c["case"] and not c["strategy"]]
    return {
        "execution_accuracy": acc,
        "best_fixed": best_fixed,
        "best_fixed_arm": max(fixed, key=fixed.get),
        "oracle": oracle,
        "improvement_vs_best_fixed": acc - best_fixed,
        "remaining_oracle_gap": oracle - acc,
        "oracle_gap_recovery": (acc - best_fixed) / (oracle - best_fixed) if oracle > best_fixed else 0.0,
        "macro_f1_vs_preferred_oracle_arm": f1_score(preferred, choices, labels=ARMS, average="macro", zero_division=0),
        "per_class_recall_vs_preferred_oracle_arm": {
            a: recall_score(preferred, choices, labels=[a], average="macro", zero_division=0) for a in ARMS
        },
        "strategy_beats_case_recall": float(np.mean([choices[i] == "strategy" for i in strategy_beats])) if strategy_beats else 0.0,
        "case_beats_strategy_recall": float(np.mean([choices[i] == "case" for i in case_beats])) if case_beats else 0.0,
        "negative_interference_avoidance_rate": float(np.mean([choices[i] != "both" for i in avoidable])) if avoidable else 0.0,
        "choice_distribution": dict(Counter(choices)),
    }


def run(label_key: str, suffix: str) -> dict[str, Any]:
    records = load_records()
    correct = [r["labels"][label_key] for r in records]
    priors = {a: float(np.mean([c[a] for c in correct])) for a in ARMS}
    preferred = [preferred_label(c, priors) for c in correct]
    results: dict[str, Any] = {}

    for mode in MODES:
        feats = [feature_subset(r, mode) for r in records]
        vec = DictVectorizer(sparse=True)
        X = vec.fit_transform(feats)
        y_bin = {a: np.array([int(c[a]) for c in correct]) for a in ARMS}
        for model_name in ["logreg", "tree", "rf", "mlp"]:
            choices = [None] * len(records)
            for train_idx, test_idx in folds_for(preferred):
                arm_probs = {}
                for arm in ARMS:
                    y = y_bin[arm]
                    if len(set(y[train_idx])) < 2:
                        arm_probs[arm] = np.full(len(test_idx), float(np.mean(y[train_idx])))
                        continue
                    clf = fresh_model(model_name)
                    clf.fit(X[train_idx], y[train_idx])
                    arm_probs[arm] = clf.predict_proba(X[test_idx])[:, 1]
                for pos, idx in enumerate(test_idx):
                    scores = {a: float(arm_probs[a][pos]) for a in ARMS}
                    choices[idx] = max(ARMS, key=lambda a: (scores[a], priors[a]))
            results[f"{mode}/{model_name}"] = evaluate(records, choices, label_key, preferred)

    out_name = "selector_stage3_1" + (f"_{suffix}" if suffix else "") + ".json"
    json.dump(results, open(os.path.join(OUT, out_name), "w"), indent=2, ensure_ascii=False)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label-key", default="full_doc_prog_correct")
    ap.add_argument("--suffix", default="")
    args = ap.parse_args()
    run(args.label_key, args.suffix)
