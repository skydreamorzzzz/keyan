"""Fixed-candidate Stage 4B audit without cross-candidate winner picking."""
from __future__ import annotations

import json
import os
import numpy as np

from run_development_nested import (
    choices_flat_delta,
    choices_gain_harm,
    choices_hierarchical,
    conservative_select,
    eval_choices,
    fit_flat_delta,
    fit_gain_harm,
    fit_hierarchical,
    inner_candidates,
)
from stage4b_common import OUT, evaluate_expected, evaluate_realized_by_replicate, folds_for_groups, load_stage4a_records, load_stage4a_synthetic

FIXED = [
    {"architecture": "flat_delta", "feature_set": "existing_meta_plus_compatibility"},
    {"architecture": "hierarchical", "feature_set": "existing_meta_plus_compatibility"},
    {"architecture": "hierarchical", "feature_set": "synthetic_interaction"},
    {"architecture": "gain_harm", "feature_set": "synthetic_interaction"},
]


def select_params_for_fixed(records, synthetic, train_idx, groups, arch, fs):
    cands = [
        c for c in inner_candidates(records, synthetic, train_idx, groups)
        if c["architecture"] == arch and c["feature_set"] == fs
    ]
    return conservative_select(cands, one_se=True)


def predict(records, synthetic, selected, train_idx, test_idx):
    arch, fs = selected["architecture"], selected["feature_set"]
    if arch == "flat_delta":
        return choices_flat_delta(fit_flat_delta(records, synthetic, fs, train_idx, test_idx), test_idx, selected["threshold"])
    if arch == "gain_harm":
        return choices_gain_harm(fit_gain_harm(records, synthetic, fs, train_idx, test_idx), test_idx, selected["threshold"], selected["lambda"])
    if arch == "hierarchical":
        return choices_hierarchical(fit_hierarchical(records, synthetic, fs, train_idx, test_idx), test_idx, selected["threshold"])
    raise ValueError(arch)


def run():
    records = load_stage4a_records()
    synthetic = load_stage4a_synthetic()
    groups = [r["annual_report_group"] for r in records]
    out = {}
    for cfg in FIXED:
        choices = ["both"] * len(records)
        selections = []
        for train_idx, test_idx in folds_for_groups(groups, n_splits=5):
            selected = select_params_for_fixed(records, synthetic, np.array(train_idx), groups, cfg["architecture"], cfg["feature_set"])
            pred = predict(records, synthetic, selected, np.array(train_idx), np.array(test_idx))
            for idx, action in pred.items():
                choices[idx] = action
            selections.append({k: v for k, v in selected.items() if k != "fold_utils"})
        name = f"{cfg['architecture']}/{cfg['feature_set']}"
        out[name] = {
            "fold_selections": selections,
            "expected_evaluation": evaluate_expected(records, choices, "annual_report_group"),
            "realized_by_replicate": evaluate_realized_by_replicate(records, choices),
        }
        print(name, out[name]["expected_evaluation"]["gain_vs_both"], out[name]["expected_evaluation"]["deviation_coverage"])
    json.dump(out, open(os.path.join(OUT, "fixed_candidate_audit.json"), "w"), indent=2, ensure_ascii=False)
    return out


if __name__ == "__main__":
    run()
