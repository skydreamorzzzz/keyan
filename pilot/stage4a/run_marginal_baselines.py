"""Nested grouped CV baselines for Stage 4A marginal utility learnability."""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from statistics import mean
from typing import Any

import numpy as np
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

OUT = os.path.dirname(__file__)
DEVIATIONS = ["none", "case", "strategy"]
ARMS = ["none", "case", "strategy", "both"]
BOOTSTRAP_SEED = 20260816
BOOTSTRAP_B = 10000


def load_records() -> list[dict[str, Any]]:
    return [json.loads(line) for line in open(os.path.join(OUT, "marginal_utility_dataset.jsonl"))]


def load_synthetic() -> dict[int, dict[str, float]]:
    path = os.path.join(OUT, "synthetic_features.jsonl")
    if not os.path.exists(path):
        return {}
    return {json.loads(line)["sample_index"]: json.loads(line)["features"] for line in open(path)}


SYNTHETIC_GROUPS = {
    "scale": {
        "percent_or_ratio_output",
        "absolute_value_output",
        "unit_scale_risk",
        "case_scale_compatibility",
        "strategy_scale_compatibility",
    },
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
}


def synthetic_subset(synth: dict[str, float], name: str) -> dict[str, float]:
    if name == "all":
        return dict(synth)
    keys = SYNTHETIC_GROUPS[name]
    return {k: v for k, v in synth.items() if k in keys}


def feature_dict(rec: dict[str, Any], feature_set: str, synthetic: dict[int, dict[str, float]]) -> dict[str, float]:
    existing = rec["features"]
    synth = synthetic.get(rec["sample_index"], {})
    if feature_set == "synthetic":
        return dict(synth)
    if feature_set in {"synthetic_scale", "synthetic_compatibility", "synthetic_interaction"}:
        return synthetic_subset(synth, feature_set.replace("synthetic_", ""))
    if feature_set == "existing_meta":
        return {k: v for k, v in existing.items() if "_emb64_" not in k}
    if feature_set == "existing_all":
        return dict(existing)
    if feature_set == "existing_meta_plus_synthetic":
        out = {k: v for k, v in existing.items() if "_emb64_" not in k}
        out.update({f"synth_{k}": v for k, v in synth.items()})
        return out
    if feature_set in {"existing_meta_plus_scale", "existing_meta_plus_compatibility", "existing_meta_plus_interaction"}:
        group = feature_set.replace("existing_meta_plus_", "")
        out = {k: v for k, v in existing.items() if "_emb64_" not in k}
        out.update({f"synth_{k}": v for k, v in synthetic_subset(synth, group).items()})
        return out
    if feature_set == "existing_all_plus_synthetic":
        out = dict(existing)
        out.update({f"synth_{k}": v for k, v in synth.items()})
        return out
    raise ValueError(feature_set)


def reg_model(name: str):
    if name == "ridge":
        return make_pipeline(StandardScaler(with_mean=False), Ridge(alpha=1.0))
    if name == "tree":
        return DecisionTreeRegressor(max_depth=3, min_samples_leaf=12, random_state=20260816)
    if name == "rf":
        return RandomForestRegressor(n_estimators=100, max_depth=4, min_samples_leaf=8, random_state=20260816)
    raise ValueError(name)


def clf_model(name: str):
    if name == "logreg":
        return make_pipeline(StandardScaler(with_mean=False), LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5))
    if name == "tree":
        return DecisionTreeClassifier(max_depth=3, min_samples_leaf=12, class_weight="balanced", random_state=20260816)
    if name == "rf":
        return RandomForestClassifier(n_estimators=100, max_depth=4, min_samples_leaf=8, class_weight="balanced", random_state=20260816)
    raise ValueError(name)


def folds(groups: list[str], n_splits: int = 5):
    n_unique = len(set(groups))
    k = min(n_splits, n_unique)
    return GroupKFold(n_splits=k).split(np.zeros(len(groups)), None, groups)


def p_correct(records: list[dict[str, Any]], idx: int, arm: str) -> float:
    return float(records[idx]["targets"]["p_correct"][arm])


def best_threshold_reg(records, X, groups, train_idx, model_name):
    thresholds = [0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.33]
    if len(set(groups[i] for i in train_idx)) < 3:
        return 0.0
    scores_by_t = defaultdict(list)
    train_idx = np.array(train_idx)
    inner_groups = [groups[i] for i in train_idx]
    for inner_train_pos, val_pos in folds(inner_groups, n_splits=3):
        inner_train = train_idx[inner_train_pos]
        val = train_idx[val_pos]
        preds = {}
        for arm in DEVIATIONS:
            y = np.array([records[i]["targets"]["deviations"][arm]["delta"] for i in inner_train])
            m = reg_model(model_name)
            m.fit(X[inner_train], y)
            preds[arm] = m.predict(X[val])
        for t in thresholds:
            vals = []
            for pos, idx in enumerate(val):
                arm_scores = {a: float(preds[a][pos]) for a in DEVIATIONS}
                best = max(DEVIATIONS, key=lambda a: arm_scores[a])
                choice = best if arm_scores[best] > t else "both"
                vals.append(p_correct(records, idx, choice))
            scores_by_t[t].append(mean(vals))
    return max(thresholds, key=lambda t: (mean(scores_by_t[t]), -t))


def best_params_gainharm(records, X, groups, train_idx, model_name):
    lambdas = [0.5, 1.0, 1.5, 2.0]
    thresholds = [0.0, 0.02, 0.05, 0.1, 0.15]
    if len(set(groups[i] for i in train_idx)) < 3:
        return 1.0, 0.0
    train_idx = np.array(train_idx)
    inner_groups = [groups[i] for i in train_idx]
    scores = defaultdict(list)
    for inner_train_pos, val_pos in folds(inner_groups, n_splits=3):
        inner_train = train_idx[inner_train_pos]
        val = train_idx[val_pos]
        gain_probs, harm_probs = {}, {}
        for arm in DEVIATIONS:
            for target_name, sink in [("gain", gain_probs), ("harm", harm_probs)]:
                y = np.array([int(records[i]["targets"]["deviations"][arm][target_name] > 0) for i in inner_train])
                if len(set(y)) < 2:
                    sink[arm] = np.full(len(val), float(np.mean(y)))
                else:
                    m = clf_model(model_name)
                    m.fit(X[inner_train], y)
                    sink[arm] = m.predict_proba(X[val])[:, 1]
        for lam in lambdas:
            for t in thresholds:
                vals = []
                for pos, idx in enumerate(val):
                    arm_scores = {a: float(gain_probs[a][pos] - lam * harm_probs[a][pos]) for a in DEVIATIONS}
                    best = max(DEVIATIONS, key=lambda a: arm_scores[a])
                    choice = best if arm_scores[best] > t else "both"
                    vals.append(p_correct(records, idx, choice))
                scores[(lam, t)].append(mean(vals))
    return max(scores, key=lambda p: (mean(scores[p]), -p[1], -p[0]))


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
    point = float(np.mean([d for vals_ in group_to_vals.values() for d in vals_]))
    return {
        "point_estimate": point,
        "ci95": [float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975))],
        "bootstrap_resamples": BOOTSTRAP_B,
        "random_seed": BOOTSTRAP_SEED,
        "procedure": f"cluster percentile bootstrap by {group_key}",
    }


def query_bootstrap(diff_by_idx: dict[int, float]) -> dict[str, Any]:
    vals = np.array(list(diff_by_idx.values()), dtype=float)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = rng.choice(len(vals), size=(BOOTSTRAP_B, len(vals)), replace=True)
    boot = vals[draws].mean(axis=1)
    return {
        "point_estimate": float(vals.mean()),
        "ci95": [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))],
        "bootstrap_resamples": BOOTSTRAP_B,
        "random_seed": BOOTSTRAP_SEED,
        "procedure": "secondary paired percentile bootstrap over queries",
    }


def evaluate(records: list[dict[str, Any]], choices: list[str], group_key: str) -> dict[str, Any]:
    n = len(records)
    acc = float(mean(p_correct(records, i, choices[i]) for i in range(n)))
    both = float(mean(p_correct(records, i, "both") for i in range(n)))
    oracle = float(mean(max(p_correct(records, i, a) for a in ARMS) for i in range(n)))
    deviated = [i for i, c in enumerate(choices) if c != "both"]
    beneficial = [i for i in deviated if records[i]["targets"]["deviations"][choices[i]]["delta"] > 0]
    harmful = [i for i in deviated if records[i]["targets"]["deviations"][choices[i]]["delta"] < 0]
    possible = [i for i in range(n) if max(records[i]["targets"]["deviations"][a]["delta"] for a in DEVIATIONS) > 0]
    diff = {i: p_correct(records, i, choices[i]) - p_correct(records, i, "both") for i in range(n)}
    return {
        "accuracy": acc,
        "always_both": both,
        "oracle": oracle,
        "gain_vs_both": acc - both,
        "oracle_gap": oracle - both,
        "oracle_gap_recovery": (acc - both) / (oracle - both) if oracle > both else 0.0,
        "regret_vs_oracle": oracle - acc,
        "deviation_coverage": len(deviated) / n,
        "deviation_count": len(deviated),
        "deviation_precision": len(beneficial) / len(deviated) if deviated else 0.0,
        "deviation_recall": len(set(beneficial) & set(possible)) / len(possible) if possible else 0.0,
        "harmful_deviation_rate": len(harmful) / len(deviated) if deviated else 0.0,
        "beneficial_deviation_count": len(beneficial),
        "harmful_deviation_count": len(harmful),
        "net_benefit_sum": float(sum(diff.values())),
        "choice_distribution": dict(Counter(choices)),
        "cluster_bootstrap": cluster_bootstrap(diff, records, group_key),
        "query_bootstrap_secondary": query_bootstrap(diff),
    }


def run_one(records, feature_set: str, formulation: str, model_name: str, group_key: str, synthetic):
    feats = [feature_dict(r, feature_set, synthetic) for r in records]
    X = DictVectorizer(sparse=True).fit_transform(feats)
    groups = [r[group_key] for r in records]
    choices = ["both"] * len(records)
    fold_params = []
    for train_idx, test_idx in folds(groups, n_splits=5):
        train_idx = np.array(train_idx)
        test_idx = np.array(test_idx)
        if formulation == "delta_regression":
            threshold = best_threshold_reg(records, X, groups, train_idx, model_name)
            preds = {}
            for arm in DEVIATIONS:
                y = np.array([records[i]["targets"]["deviations"][arm]["delta"] for i in train_idx])
                m = reg_model(model_name)
                m.fit(X[train_idx], y)
                preds[arm] = m.predict(X[test_idx])
            for pos, idx in enumerate(test_idx):
                scores = {a: float(preds[a][pos]) for a in DEVIATIONS}
                best = max(DEVIATIONS, key=lambda a: scores[a])
                choices[idx] = best if scores[best] > threshold else "both"
            fold_params.append({"threshold": threshold})
        elif formulation == "gain_harm":
            lam, threshold = best_params_gainharm(records, X, groups, train_idx, model_name)
            gain_probs, harm_probs = {}, {}
            for arm in DEVIATIONS:
                for target_name, sink in [("gain", gain_probs), ("harm", harm_probs)]:
                    y = np.array([int(records[i]["targets"]["deviations"][arm][target_name] > 0) for i in train_idx])
                    if len(set(y)) < 2:
                        sink[arm] = np.full(len(test_idx), float(np.mean(y)))
                    else:
                        m = clf_model(model_name)
                        m.fit(X[train_idx], y)
                        sink[arm] = m.predict_proba(X[test_idx])[:, 1]
            for pos, idx in enumerate(test_idx):
                scores = {a: float(gain_probs[a][pos] - lam * harm_probs[a][pos]) for a in DEVIATIONS}
                best = max(DEVIATIONS, key=lambda a: scores[a])
                choices[idx] = best if scores[best] > threshold else "both"
            fold_params.append({"lambda": lam, "threshold": threshold})
        else:
            raise ValueError(formulation)
    result = evaluate(records, choices, group_key)
    result["fold_params"] = fold_params
    return result


def run(group_key: str = "annual_report_group", selected_feature_sets: list[str] | None = None) -> dict[str, Any]:
    records = load_records()
    synthetic = load_synthetic()
    feature_sets = selected_feature_sets or ["existing_meta", "existing_all"]
    if synthetic:
        if selected_feature_sets is None:
            feature_sets += [
                "synthetic",
                "synthetic_scale",
                "synthetic_compatibility",
                "synthetic_interaction",
                "existing_meta_plus_scale",
                "existing_meta_plus_compatibility",
                "existing_meta_plus_interaction",
                "existing_meta_plus_synthetic",
                "existing_all_plus_synthetic",
            ]
    results = {}
    for feature_set in feature_sets:
        for formulation, models in [
            ("delta_regression", ["ridge", "tree", "rf"]),
            ("gain_harm", ["logreg", "tree", "rf"]),
        ]:
            for model_name in models:
                name = f"{feature_set}/{formulation}/{model_name}"
                results[name] = run_one(records, feature_set, formulation, model_name, group_key, synthetic)
                print(name, results[name]["accuracy"], results[name]["gain_vs_both"], results[name]["deviation_coverage"])
    compact = {
        "_meta": {
            "n": len(records),
            "group_key": group_key,
            "feature_sets": feature_sets,
            "formulations": ["delta_regression", "gain_harm"],
            "bootstrap": f"cluster by {group_key}",
        },
        "always_both": float(mean(p_correct(records, i, "both") for i in range(len(records)))),
        "oracle": float(mean(max(p_correct(records, i, a) for a in ARMS) for i in range(len(records)))),
        "results": results,
    }
    suffix = "annual" if group_key == "annual_report_group" else "page"
    json.dump(compact, open(os.path.join(OUT, f"marginal_baselines_{suffix}.json"), "w"), indent=2, ensure_ascii=False)
    print(json.dumps({k: v for k, v in compact.items() if k != "results"}, indent=2))
    return compact


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--group-key", choices=["annual_report_group", "page_group"], default="annual_report_group")
    ap.add_argument("--feature-sets", nargs="*", default=None)
    args = ap.parse_args()
    run(args.group_key, args.feature_sets)
