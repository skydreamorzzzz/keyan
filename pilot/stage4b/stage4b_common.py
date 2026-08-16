"""Shared utilities for Stage 4B conservative router audit."""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from statistics import mean
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STAGE4A = os.path.join(ROOT, "pilot", "stage4a")
OUT = os.path.dirname(__file__)
DEVIATIONS = ["none", "case", "strategy"]
ARMS = ["none", "case", "strategy", "both"]
BOOTSTRAP_SEED = 20260816
BOOTSTRAP_B = 10000

SYNTHETIC_GROUPS = {
    "compatibility": {
        "ratio_likelihood",
        "change_likelihood",
        "aggregation_likelihood",
        "comparison_likelihood",
        "arithmetic_depth",
        "table_heavy_reasoning",
        "case_applicability",
        "case_operation_compatibility",
        "strategy_applicability",
        "strategy_operation_compatibility",
    },
    "interaction": {
        "ambiguity_risk",
        "case_copy_risk",
        "strategy_conflict_risk",
        "case_strategy_agreement",
        "combination_overload_risk",
    },
    "scale": {
        "percent_or_ratio_output",
        "absolute_value_output",
        "unit_scale_risk",
        "case_scale_compatibility",
        "strategy_scale_compatibility",
    },
}


def load_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def annual_report_group(ex_or_name: Any) -> str:
    if isinstance(ex_or_name, dict):
        text = ex_or_name.get("filename") or ex_or_name.get("id") or ""
    else:
        text = str(ex_or_name)
    parts = str(text).split("/")
    return "/".join(parts[:2]) if len(parts) >= 2 else str(text).split("/page_")[0]


def load_stage4a_records() -> list[dict[str, Any]]:
    return [json.loads(line) for line in open(os.path.join(STAGE4A, "marginal_utility_dataset.jsonl"))]


def load_stage4a_synthetic() -> dict[int, dict[str, float]]:
    return {json.loads(line)["sample_index"]: json.loads(line)["features"] for line in open(os.path.join(STAGE4A, "synthetic_features.jsonl"))}


def synthetic_subset(synth: dict[str, float], group: str) -> dict[str, float]:
    return {k: v for k, v in synth.items() if k in SYNTHETIC_GROUPS[group]}


def feature_dict(rec: dict[str, Any], feature_set: str, synthetic: dict[int, dict[str, float]]) -> dict[str, float]:
    existing = rec["features"]
    synth = synthetic.get(rec["sample_index"], rec.get("synthetic_features", {}))
    if feature_set == "existing_meta":
        return {k: v for k, v in existing.items() if "_emb64_" not in k}
    if feature_set == "existing_meta_plus_compatibility":
        out = {k: v for k, v in existing.items() if "_emb64_" not in k}
        out.update({f"synth_{k}": v for k, v in synthetic_subset(synth, "compatibility").items()})
        return out
    if feature_set == "synthetic_interaction":
        return synthetic_subset(synth, "interaction")
    if feature_set == "existing_meta_plus_interaction":
        out = {k: v for k, v in existing.items() if "_emb64_" not in k}
        out.update({f"synth_{k}": v for k, v in synthetic_subset(synth, "interaction").items()})
        return out
    raise ValueError(feature_set)


def folds_for_groups(groups: list[str], n_splits: int = 5):
    k = min(n_splits, len(set(groups)))
    return GroupKFold(n_splits=k).split(np.zeros(len(groups)), None, groups)


def p_correct(records: list[dict[str, Any]], idx: int, arm: str) -> float:
    return float(records[idx]["targets"]["p_correct"][arm])


def action_correct_expected(records: list[dict[str, Any]], idx: int, action: str) -> float:
    return p_correct(records, idx, action)


def override_positive(rec: dict[str, Any]) -> int:
    return int(max(rec["targets"]["deviations"][a]["delta"] for a in DEVIATIONS) > 0)


def best_deviation_label(rec: dict[str, Any]) -> str:
    return max(DEVIATIONS, key=lambda a: (rec["targets"]["deviations"][a]["delta"], a == "strategy", a == "none"))


def reg_model():
    return make_pipeline(StandardScaler(with_mean=False), Ridge(alpha=1.0))


def logreg_model():
    return make_pipeline(StandardScaler(with_mean=False), LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5))


def rf_classifier():
    return RandomForestClassifier(n_estimators=100, max_depth=4, min_samples_leaf=8, class_weight="balanced", random_state=20260816)


def vectorize_train_test(records, synthetic, feature_set, train_idx, test_idx):
    vec = DictVectorizer(sparse=True)
    x_train = vec.fit_transform([feature_dict(records[i], feature_set, synthetic) for i in train_idx])
    x_test = vec.transform([feature_dict(records[i], feature_set, synthetic) for i in test_idx])
    return vec, x_train, x_test


def conservative_select(candidates: list[dict[str, Any]], one_se: bool = True) -> dict[str, Any]:
    """Select by one-standard-error, then conservative coverage/gating."""
    best_mean = max(c["mean_utility"] for c in candidates)
    best = max(candidates, key=lambda c: c["mean_utility"])
    cutoff = best_mean - best.get("se_utility", 0.0) if one_se else best_mean
    eligible = [c for c in candidates if c["mean_utility"] >= cutoff - 1e-12]
    return max(
        eligible,
        key=lambda c: (
            -c.get("coverage", 0.0),
            c.get("threshold", 0.0),
            c.get("lambda", 0.0),
            c.get("mean_utility", 0.0),
        ),
    )


def cluster_bootstrap(diff_by_idx: dict[int, float], records: list[dict[str, Any]], group_key: str) -> dict[str, Any]:
    group_to_vals = defaultdict(list)
    for i, d in diff_by_idx.items():
        group_to_vals[records[i][group_key]].append(d)
    groups = sorted(group_to_vals)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    vals = []
    for _ in range(BOOTSTRAP_B):
        chosen = rng.choice(groups, size=len(groups), replace=True)
        sample = [x for g in chosen for x in group_to_vals[g]]
        vals.append(float(np.mean(sample)))
    point = float(np.mean([d for xs in group_to_vals.values() for d in xs]))
    return {
        "point_estimate": point,
        "ci95": [float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975))],
        "bootstrap_resamples": BOOTSTRAP_B,
        "random_seed": BOOTSTRAP_SEED,
        "procedure": f"cluster percentile bootstrap by {group_key}",
    }


def evaluate_expected(records: list[dict[str, Any]], choices: list[str], group_key: str = "annual_report_group") -> dict[str, Any]:
    n = len(records)
    acc = float(mean(action_correct_expected(records, i, choices[i]) for i in range(n)))
    both = float(mean(p_correct(records, i, "both") for i in range(n)))
    oracle = float(mean(max(p_correct(records, i, a) for a in ARMS) for i in range(n)))
    deviated = [i for i, c in enumerate(choices) if c != "both"]
    beneficial = [i for i in deviated if records[i]["targets"]["deviations"][choices[i]]["delta"] > 0]
    harmful = [i for i in deviated if records[i]["targets"]["deviations"][choices[i]]["delta"] < 0]
    diff = {i: action_correct_expected(records, i, choices[i]) - p_correct(records, i, "both") for i in range(n)}
    return {
        "accuracy": acc,
        "always_both": both,
        "oracle": oracle,
        "gain_vs_both": acc - both,
        "oracle_gap": oracle - both,
        "oracle_gap_recovery": (acc - both) / (oracle - both) if oracle > both else 0.0,
        "deviation_coverage": len(deviated) / n,
        "deviation_count": len(deviated),
        "deviation_precision": len(beneficial) / len(deviated) if deviated else 0.0,
        "harmful_deviation_rate": len(harmful) / len(deviated) if deviated else 0.0,
        "beneficial_deviation_count": len(beneficial),
        "harmful_deviation_count": len(harmful),
        "choice_distribution": dict(Counter(choices)),
        "cluster_bootstrap": cluster_bootstrap(diff, records, group_key),
    }


def evaluate_realized_by_replicate(records: list[dict[str, Any]], choices: list[str]) -> dict[str, Any]:
    out = {}
    for rep in ["rn1", "rn2", "rn3"]:
        policy = [int(records[i]["replicate_correctness"][rep][choices[i]]) for i in range(len(records))]
        both = [int(records[i]["replicate_correctness"][rep]["both"]) for i in range(len(records))]
        out[rep] = {
            "policy_accuracy": float(mean(policy)),
            "both_accuracy": float(mean(both)),
            "gain_vs_both": float(mean(np.array(policy) - np.array(both))),
        }
    gains = [v["gain_vs_both"] for v in out.values()]
    out["_summary"] = {"mean_gain": float(mean(gains)), "min_gain": float(min(gains)), "max_gain": float(max(gains)), "range": float(max(gains) - min(gains))}
    return out


def estimate_tokens(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9_%.$/-]+|[^\s]", text or ""))
