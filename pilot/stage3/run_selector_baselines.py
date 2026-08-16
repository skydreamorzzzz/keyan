"""Lightweight offline selector baselines for Stage 3.

The selector is trained with 5-fold CV on inference-time-safe fields only.
It predicts per-arm utility with independent binary classifiers and executes
the arm with the highest predicted probability.
"""
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
from sklearn.metrics import classification_report, f1_score, recall_score
from sklearn.model_selection import KFold, StratifiedKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

OUT = os.path.dirname(__file__)
ARMS = ["none", "case", "strategy", "both"]


def load_records() -> list[dict[str, Any]]:
    return [json.loads(line) for line in open(os.path.join(OUT, "oracle_analysis_dataset.jsonl"))]


def feature_subset(features: dict[str, Any], mode: str) -> dict[str, float]:
    out = {}
    for k, v in features.items():
        if isinstance(v, bool):
            v = int(v)
        if not isinstance(v, (int, float)):
            continue
        is_retrieval = k.startswith(("case_", "strategy_", "retrieval_", "both_"))
        is_repr = "_emb64_" in k
        if mode == "query_only" and is_retrieval:
            continue
        if mode == "query_retrieval_meta" and is_repr:
            continue
        out[k] = float(v)
    return out


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
        return make_pipeline(StandardScaler(with_mean=False), MLPClassifier(hidden_layer_sizes=(32,), alpha=0.01, max_iter=800, random_state=20260816))
    raise ValueError(name)


def evaluate_choice(records: list[dict[str, Any]], choices: list[str], label_key: str, preferred: list[str]) -> dict[str, Any]:
    correct = [r["labels"][label_key] for r in records]
    acc = float(np.mean([correct[i][choices[i]] for i in range(len(records))]))
    fixed = {a: float(np.mean([c[a] for c in correct])) for a in ARMS}
    best_fixed = max(fixed.values())
    oracle = float(np.mean([any(c[a] for a in ARMS) for c in correct]))
    avoidable = [i for i, c in enumerate(correct) if not c["both"] and (c["case"] or c["strategy"])]
    avoided = [i for i in avoidable if choices[i] != "both"]
    strategy_only = [i for i, c in enumerate(correct) if c["strategy"] and not c["case"]]
    case_only = [i for i, c in enumerate(correct) if c["case"] and not c["strategy"]]
    return {
        "execution_accuracy": acc,
        "fixed_accuracy": fixed,
        "best_fixed": best_fixed,
        "best_fixed_arm": max(fixed, key=fixed.get),
        "oracle": oracle,
        "remaining_oracle_gap": oracle - acc,
        "improvement_vs_best_fixed": acc - best_fixed,
        "oracle_gap_recovery": (acc - best_fixed) / (oracle - best_fixed) if oracle > best_fixed else 0.0,
        "macro_f1_vs_preferred_oracle_arm": f1_score(preferred, choices, labels=ARMS, average="macro", zero_division=0),
        "per_class_recall_vs_preferred_oracle_arm": {
            a: recall_score(preferred, choices, labels=[a], average="macro", zero_division=0) for a in ARMS
        },
        "strategy_beats_case_recall": float(np.mean([choices[i] == "strategy" for i in strategy_only])) if strategy_only else 0.0,
        "case_beats_strategy_recall": float(np.mean([choices[i] == "case" for i in case_only])) if case_only else 0.0,
        "negative_interference_avoidance_rate": len(avoided) / len(avoidable) if avoidable else 0.0,
        "choice_distribution": dict(Counter(choices)),
    }


def run(label_key: str = "full_doc_prog_correct", suffix: str = "") -> dict[str, Any]:
    records = load_records()
    correct = [r["labels"][label_key] for r in records]
    priors = {a: float(np.mean([c[a] for c in correct])) for a in ARMS}
    preferred = [preferred_label(c, priors) for c in correct]
    results: dict[str, Any] = {}

    for mode in ["query_only", "query_retrieval_meta", "query_retrieved_repr"]:
        feats = [feature_subset(r["features"], mode) for r in records]
        vec = DictVectorizer(sparse=True)
        X = vec.fit_transform(feats)
        y_bin = {a: np.array([int(c[a]) for c in correct]) for a in ARMS}

        for model_name in ["logreg", "tree", "rf", "mlp"]:
            choices = [None] * len(records)
            prob_dump = []
            for train_idx, test_idx in folds_for(preferred):
                arm_probs = {}
                for arm in ARMS:
                    y = y_bin[arm]
                    if len(set(y[train_idx])) < 2:
                        arm_probs[arm] = np.full(len(test_idx), float(np.mean(y[train_idx])))
                        continue
                    clf = fresh_model(model_name)
                    clf.fit(X[train_idx], y[train_idx])
                    if hasattr(clf, "predict_proba"):
                        arm_probs[arm] = clf.predict_proba(X[test_idx])[:, 1]
                    else:
                        arm_probs[arm] = clf.predict(X[test_idx])
                for pos, idx in enumerate(test_idx):
                    scores = {a: float(arm_probs[a][pos]) for a in ARMS}
                    # Tiny prior tie-breaker, favoring empirically stronger fixed arm only on ties.
                    choice = max(ARMS, key=lambda a: (scores[a], priors[a]))
                    choices[idx] = choice
                    prob_dump.append({"sample_index": int(idx), "choice": choice, "scores": scores})
            name = f"{mode}/{model_name}"
            results[name] = evaluate_choice(records, choices, label_key, preferred)
            results[name]["cv_probabilities"] = sorted(prob_dump, key=lambda x: x["sample_index"])

    compact = {k: {kk: vv for kk, vv in v.items() if kk != "cv_probabilities"} for k, v in results.items()}
    base = "selector_baselines" + (f"_{suffix}" if suffix else "")
    json.dump(compact, open(os.path.join(OUT, base + ".json"), "w"), indent=2, ensure_ascii=False)
    json.dump(results, open(os.path.join(OUT, base + "_with_probs.json"), "w"), indent=2, ensure_ascii=False)
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return compact


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label-key", default="full_doc_prog_correct")
    ap.add_argument("--suffix", default="")
    args = ap.parse_args()
    run(args.label_key, args.suffix)
