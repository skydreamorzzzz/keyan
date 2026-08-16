"""Build Stage 3.1 inference-time retrieval utility features.

This script does not use current-query gold answers, gold programs, or arm
correctness as features. Gold-derived fields from the Stage 3 dataset are used
only to write offline proxy-quality diagnostics.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from typing import Any

import numpy as np

OUT = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(OUT, "..", ".."))
ARMS = ["none", "case", "strategy", "both"]


def load_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def records() -> list[dict[str, Any]]:
    return [json.loads(line) for line in open(os.path.join(OUT, "oracle_analysis_dataset.jsonl"))]


def norm_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?|%", (text or "").lower())


def contains_any(text: str, terms: list[str]) -> bool:
    t = " " + (text or "").lower() + " "
    return any(term in t for term in terms)


def entropy(vals: list[str]) -> float:
    if not vals:
        return 0.0
    c = Counter(vals)
    n = len(vals)
    return float(-sum((v / n) * math.log(v / n + 1e-12) for v in c.values()))


def normalize_struct(struct: list[str] | tuple[str, ...] | None) -> str:
    return ">".join(str(x) for x in struct or [])


def ops_to_family(ops: list[str] | tuple[str, ...]) -> str:
    ops = list(ops or [])
    if any(o == "greater" for o in ops):
        return "comparison"
    if any(o in ("table_average",) for o in ops):
        return "average"
    if any(o in ("table_sum", "table_max", "table_min") for o in ops):
        return "aggregation"
    if "divide" in ops and "subtract" in ops:
        return "percentage_change"
    if "divide" in ops:
        return "ratio"
    if "subtract" in ops:
        return "difference"
    if "add" in ops:
        return "aggregation"
    if "multiply" in ops:
        return "multiplication"
    return "other"


def strategy_families(strategy: dict[str, Any]) -> list[str]:
    fams = []
    for fam in strategy.get("program_family", []):
        fams.append(ops_to_family(fam))
    # Strategy text carries semantic distinctions that program families can hide.
    txt = " ".join(str(strategy.get(k, "")) for k in ["name", "problem_pattern", "template", "operand_roles", "formula"]).lower()
    if any(x in txt for x in ["change", "growth", "increase", "decrease", "cumulative return"]):
        fams.append("percentage_change")
    if any(x in txt for x in ["average", "mean"]):
        fams.append("average")
    if any(x in txt for x in ["sum", "total", "aggregate"]):
        fams.append("aggregation")
    if any(x in txt for x in ["part", "whole", "share", "portion", "ratio"]):
        fams.append("ratio")
    return sorted(set(fams)) or ["other"]


def predict_query_family(q: str) -> str:
    ql = (q or "").lower()
    has_percent = "%" in ql or contains_any(ql, [" percent ", " percentage "])
    has_change = contains_any(ql, [
        " change ", " changed ", " increase ", " increased ", " decrease ", " decreased ",
        " growth ", " decline ", " difference ", " compared ", " from ", " to ",
        " year over year ", " year-over-year ",
    ])
    if contains_any(ql, [" greater ", " higher ", " lower ", " less ", " more than ", " compare ", " compared to "]):
        return "comparison"
    if contains_any(ql, [" average ", " mean "]):
        return "average"
    if has_percent and has_change:
        return "percentage_change"
    if contains_any(ql, [" difference ", " change in ", " increase in ", " decrease in "]):
        return "difference"
    if contains_any(ql, [" per ", " ratio ", " margin ", " share ", " portion ", " as a percentage of ", " percent of ", " percentage of "]):
        return "ratio"
    if has_percent:
        return "ratio"
    if contains_any(ql, [" total ", " sum ", " combined ", " aggregate "]):
        return "aggregation"
    if contains_any(ql, [" product ", " multiply ", " times "]):
        return "multiplication"
    if contains_any(ql, [" basis point ", " basis points ", " thousand ", " thousands ", " million ", " millions ", " billion ", " billions "]):
        return "unit_scaling"
    years = re.findall(r"\b(?:19|20)\d{2}\b", ql)
    if len(set(years)) >= 2:
        return "multi_step"
    return "other"


def family_compatible(pred: str, fam: str) -> bool:
    if pred == fam:
        return True
    groups = [
        {"percentage_change", "difference"},
        {"ratio", "average"},
        {"aggregation", "average"},
        {"unit_scaling", "multiplication"},
        {"multi_step", "percentage_change", "difference", "ratio"},
    ]
    return any(pred in g and fam in g for g in groups)


def extract_roles(text: str) -> set[str]:
    q = (text or "").lower()
    roles: set[str] = set()
    if "%" in q or contains_any(q, [" percent ", " percentage "]):
        roles.add("percent_target")
    if contains_any(q, [" fraction ", " decimal "]):
        roles.add("fraction_target")
    if contains_any(q, [" per "]):
        roles.update(["numerator", "denominator", "per_unit"])
    if contains_any(q, [" ratio ", " margin "]):
        roles.update(["numerator", "denominator"])
    if contains_any(q, [" share ", " portion ", " of total ", " percent of ", " percentage of "]):
        roles.update(["part", "whole"])
    if contains_any(q, [" increase ", " increased ", " decrease ", " decreased ", " change ", " growth ", " decline ", " compared "]):
        roles.update(["old_value", "new_value"])
    if contains_any(q, [" prior ", " previous ", " earlier ", " beginning ", " initial "]):
        roles.add("old_value")
    if contains_any(q, [" current ", " ending ", " final ", " latest "]):
        roles.add("new_value")
    if contains_any(q, [" average ", " mean "]):
        roles.update(["sum_components", "count"])
    if contains_any(q, [" total ", " sum ", " combined ", " aggregate "]):
        roles.add("sum_components")
    if contains_any(q, [" greater ", " higher ", " lower ", " less ", " more than "]):
        roles.update(["left_compare", "right_compare"])
    if contains_any(q, [" volume ", " transactions ", " cards ", " units "]):
        roles.add("quantity")
    if contains_any(q, [" price ", " cost ", " expense ", " revenue ", " income ", " sales "]):
        roles.add("monetary_metric")
    if contains_any(q, [" share ", " shares ", " per share "]):
        roles.add("share_metric")
    if contains_any(q, [" thousand ", " thousands ", " million ", " millions ", " billion ", " billions ", " basis point ", " basis points "]):
        roles.add("scaling_factor")
    return roles


def years(text: str) -> list[int]:
    return [int(x) for x in re.findall(r"\b(?:19|20)\d{2}\b", text or "")]


def scale_profile(text: str, answer: Any = None, scale_text: str = "") -> dict[str, Any]:
    t = " ".join([str(text or ""), str(answer if answer is not None else ""), str(scale_text or "")]).lower()
    ans = str(answer if answer is not None else "").lower()
    profile = {
        "asks_or_outputs_percent": int("%" in t or "percent" in t or "percentage" in t),
        "fraction_convention": int("fraction" in t or "0-1" in t or bool(re.search(r"\b0\.\d+", ans))),
        "raw_number_convention": int(not ("%" in ans or "percent" in ans or "fraction" in t or "0-1" in t)),
        "has_million": int("million" in t),
        "has_billion": int("billion" in t),
        "has_thousand": int("thousand" in t),
        "has_basis_points": int("basis point" in t),
    }
    profile["has_scale_word"] = int(profile["has_million"] or profile["has_billion"] or profile["has_thousand"] or profile["has_basis_points"])
    return profile


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if (a | b) else 0.0


def add_onehot(feats: dict[str, float], prefix: str, value: str) -> None:
    feats[f"{prefix}_{value}"] = 1.0


def summarize_alignment(records_out: list[dict[str, Any]]) -> dict[str, Any]:
    def metric(preds, golds):
        tp = sum(p and g for p, g in zip(preds, golds))
        fp = sum(p and not g for p, g in zip(preds, golds))
        fn = sum((not p) and g for p, g in zip(preds, golds))
        tn = sum((not p) and (not g) for p, g in zip(preds, golds))
        return {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "recall": tp / (tp + fn) if tp + fn else 0.0,
            "accuracy": (tp + tn) / max(1, tp + fp + fn + tn),
        }

    qfam_acc = Counter()
    n = len(records_out)
    for r in records_out:
        pred = r["stage3_1"]["predicted_query_family"]
        gold = r["analysis"]["gold_operation_family"]
        qfam_acc["exact"] += int(pred == gold)
        qfam_acc["compatible"] += int(family_compatible(pred, gold))

    case_pred = [r["stage3_1"]["proxy"]["case_predicted_family_agreement"] for r in records_out]
    case_gold = [r["analysis"]["case_family_consistency_gold"]["any_same_struct"] for r in records_out]
    strat_pred = [r["stage3_1"]["proxy"]["strategy_predicted_family_agreement"] for r in records_out]
    strat_gold = [r["analysis"]["strategy_family_consistency_gold"]["any_matches"] for r in records_out]

    return {
        "n": n,
        "predicted_query_family_vs_gold_operation": {
            "exact_accuracy": qfam_acc["exact"] / n,
            "compatible_accuracy": qfam_acc["compatible"] / n,
            "predicted_distribution": dict(Counter(r["stage3_1"]["predicted_query_family"] for r in records_out)),
            "gold_distribution": dict(Counter(r["analysis"]["gold_operation_family"] for r in records_out)),
        },
        "case_predicted_family_agreement_as_proxy_for_gold_struct_hit": metric(case_pred, case_gold),
        "strategy_predicted_family_agreement_as_proxy_for_gold_struct_hit": metric(strat_pred, strat_gold),
    }


def build() -> None:
    base_records = records()
    cases = {x["case_id"]: x for x in load_json(os.path.join(ROOT, "pilot", "output", "case_memory.json"))}
    strategies = {x["strategy_id"]: x for x in load_json(os.path.join(ROOT, "pilot", "output", "strategies_clean.json"))}
    out_records = []

    for rec in base_records:
        q = rec["question"]
        q_roles = extract_roles(q)
        q_years = years(q)
        q_scale = scale_profile(q)
        pred_family = predict_query_family(q)

        feats: dict[str, float] = {}
        add_onehot(feats, "pred_family", pred_family)
        feats["pred_family_is_ratio_like"] = float(pred_family in {"ratio", "average"})
        feats["pred_family_is_change_like"] = float(pred_family in {"percentage_change", "difference"})
        feats["pred_family_is_scale_like"] = float(pred_family in {"unit_scaling", "multiplication"})
        feats["query_role_count"] = float(len(q_roles))
        for role in sorted(q_roles):
            feats[f"query_role_{role}"] = 1.0

        case_fams, case_structs, case_roles, case_steps = [], [], [], []
        case_scale_mismatches = []
        case_role_overlaps = []
        case_year_compat = []
        case_symbolic_compat = []
        case_scale_profiles = []
        for item in rec["retrieval"]["case"]:
            cm = cases[item["case_id"]]
            cfam = ops_to_family(cm.get("struct", []))
            cstruct = normalize_struct(cm.get("struct"))
            ctext = " ".join([cm.get("question", ""), " ".join(cm.get("gold_facts", [])), cm.get("program_re", "")])
            roles = extract_roles(ctext)
            cyrs = years(ctext)
            cscale = scale_profile(ctext, cm.get("answer"))
            case_fams.append(cfam)
            case_structs.append(cstruct)
            case_roles.append(roles)
            case_steps.append(float(cm.get("n_steps") or 0))
            case_role_overlaps.append(jaccard(q_roles, roles))
            case_year_compat.append(float((len(q_years) == 0 and len(cyrs) == 0) or (min(len(q_years), 2) == min(len(cyrs), 2))))
            case_symbolic_compat.append(float(family_compatible(pred_family, cfam)))
            case_scale_profiles.append(cscale)
            mismatch = int(q_scale["asks_or_outputs_percent"] != cscale["asks_or_outputs_percent"])
            mismatch += int(q_scale["has_scale_word"] and not cscale["has_scale_word"])
            case_scale_mismatches.append(float(mismatch > 0))

        strat_fams, strat_roles, strat_scale_mismatches, strat_role_overlaps = [], [], [], []
        strat_structs = []
        strat_scale_profiles = []
        for item in rec["retrieval"]["strategy"]:
            sm = strategies[item["strategy_id"]]
            sfams = strategy_families(sm)
            stext = " ".join(str(sm.get(k, "")) for k in ["name", "problem_pattern", "operand_roles", "procedure", "formula", "template", "unit_convention", "canonical_output_scale"])
            roles = extract_roles(stext)
            sscale = scale_profile(stext, None, sm.get("canonical_output_scale", ""))
            strat_fams.extend(sfams)
            strat_structs.extend(normalize_struct(fam) for fam in sm.get("program_family", []))
            strat_roles.append(roles)
            strat_role_overlaps.append(jaccard(q_roles, roles))
            strat_scale_profiles.append(sscale)
            mismatch = int(q_scale["asks_or_outputs_percent"] != sscale["asks_or_outputs_percent"])
            mismatch += int(q_scale["has_scale_word"] and not sscale["has_scale_word"])
            strat_scale_mismatches.append(float(mismatch > 0))

        case_agree = [family_compatible(pred_family, f) for f in case_fams]
        strat_agree = [family_compatible(pred_family, f) for f in strat_fams]
        case_struct_counts = Counter(case_structs)
        strat_struct_counts = Counter(strat_structs)
        case_fam_counts = Counter(case_fams)
        strat_fam_counts = Counter(strat_fams)
        top_case_fam = case_fams[0] if case_fams else "none"
        top_strat_fam = strat_fams[0] if strat_fams else "none"

        # Predicted-family proxy features.
        feats["case_pred_family_top1_agree"] = float(case_agree[0]) if case_agree else 0.0
        feats["case_pred_family_any_agree"] = float(any(case_agree))
        feats["case_pred_family_agree_ratio"] = float(np.mean(case_agree)) if case_agree else 0.0
        feats["strategy_pred_family_any_agree"] = float(any(strat_agree))
        feats["strategy_pred_family_agree_ratio"] = float(np.mean(strat_agree)) if strat_agree else 0.0
        feats["case_strategy_pred_family_both_agree"] = float(any(case_agree) and any(strat_agree))
        feats["case_strategy_family_disagreement"] = float(top_case_fam != top_strat_fam)
        add_onehot(feats, "case_top_pred_family", top_case_fam)
        add_onehot(feats, "strategy_top_pred_family", top_strat_fam)

        # Operand/structure alignment.
        feats["case_role_overlap_top1"] = case_role_overlaps[0] if case_role_overlaps else 0.0
        feats["case_role_overlap_mean"] = float(np.mean(case_role_overlaps)) if case_role_overlaps else 0.0
        feats["strategy_role_overlap_mean"] = float(np.mean(strat_role_overlaps)) if strat_role_overlaps else 0.0
        feats["case_year_compat_top1"] = case_year_compat[0] if case_year_compat else 0.0
        feats["case_year_compat_mean"] = float(np.mean(case_year_compat)) if case_year_compat else 0.0
        feats["case_symbolic_compat_top1"] = case_symbolic_compat[0] if case_symbolic_compat else 0.0
        feats["case_symbolic_compat_mean"] = float(np.mean(case_symbolic_compat)) if case_symbolic_compat else 0.0
        feats["case_step_distance_top1"] = abs((case_steps[0] if case_steps else 0.0) - max(1.0, len(q_roles) / 2.5))
        feats["case_step_entropy_proxy"] = float(np.std(case_steps)) if case_steps else 0.0
        feats["case_struct_mode_share"] = case_struct_counts.most_common(1)[0][1] / len(case_structs) if case_structs else 0.0
        feats["strategy_struct_mode_share"] = strat_struct_counts.most_common(1)[0][1] / len(strat_structs) if strat_structs else 0.0
        feats["case_family_mode_share"] = case_fam_counts.most_common(1)[0][1] / len(case_fams) if case_fams else 0.0
        feats["strategy_family_mode_share"] = strat_fam_counts.most_common(1)[0][1] / len(strat_fams) if strat_fams else 0.0
        feats["case_struct_entropy_31"] = entropy(case_structs)
        feats["strategy_struct_entropy_31"] = entropy(strat_structs)
        feats["case_family_entropy_31"] = entropy(case_fams)
        feats["strategy_family_entropy_31"] = entropy(strat_fams)

        # Unit/scale compatibility.
        for k, v in q_scale.items():
            feats[f"query_scale_{k}"] = float(v)
        feats["case_scale_mismatch_top1"] = case_scale_mismatches[0] if case_scale_mismatches else 0.0
        feats["case_scale_mismatch_mean"] = float(np.mean(case_scale_mismatches)) if case_scale_mismatches else 0.0
        feats["strategy_scale_mismatch_mean"] = float(np.mean(strat_scale_mismatches)) if strat_scale_mismatches else 0.0
        feats["case_strategy_scale_disagreement"] = float(bool(case_scale_profiles and strat_scale_profiles) and case_scale_profiles[0]["fraction_convention"] != strat_scale_profiles[0]["fraction_convention"])
        feats["scale_pollution_risk_case_fraction_for_percent_query"] = float(q_scale["asks_or_outputs_percent"] and bool(case_scale_profiles) and case_scale_profiles[0]["fraction_convention"])
        feats["scale_pollution_risk_strategy_fraction_for_percent_query"] = float(q_scale["asks_or_outputs_percent"] and bool(strat_scale_profiles) and strat_scale_profiles[0]["fraction_convention"])

        # Retrieval semantic consistency interaction.
        old = rec["features"]
        feats["case_score_x_pred_family_agree"] = float(old.get("case_top_score", 0.0) * feats["case_pred_family_top1_agree"])
        feats["strategy_score_x_pred_family_agree"] = float(old.get("strategy_top_score", 0.0) * feats["strategy_pred_family_any_agree"])
        feats["case_score_x_role_overlap"] = float(old.get("case_top_score", 0.0) * feats["case_role_overlap_top1"])
        feats["case_top_conflict_with_rest"] = float(bool(case_fams) and case_fam_counts[top_case_fam] == 1 and len(case_fams) > 1)
        feats["strategy_top_conflict_with_rest"] = float(bool(strat_fams) and strat_fam_counts[top_strat_fam] == 1 and len(strat_fams) > 1)
        feats["retrieval_alignment_high_conf"] = float(
            feats["case_pred_family_any_agree"] and feats["strategy_pred_family_any_agree"]
            and feats["case_role_overlap_mean"] >= 0.25
            and feats["case_scale_mismatch_mean"] < 0.75
        )
        feats["retrieval_alignment_low_conf"] = float(
            feats["case_pred_family_any_agree"] == 0
            and feats["strategy_pred_family_any_agree"] == 0
            and feats["case_role_overlap_mean"] < 0.2
        )

        enriched = dict(rec)
        enriched["stage3_1"] = {
            "feature_version": "stage3_1_rules_v1",
            "feature_safety": "inference-time safe; gold fields only in analysis/proxy diagnostics",
            "predicted_query_family": pred_family,
            "query_roles": sorted(q_roles),
            "query_scale_profile": q_scale,
            "case_predicted_families": case_fams,
            "strategy_predicted_families": sorted(set(strat_fams)),
            "proxy": {
                "case_predicted_family_agreement": bool(any(case_agree)),
                "strategy_predicted_family_agreement": bool(any(strat_agree)),
                "case_predicted_family_agree_ratio": feats["case_pred_family_agree_ratio"],
                "strategy_predicted_family_agree_ratio": feats["strategy_pred_family_agree_ratio"],
                "retrieval_alignment_high_conf": bool(feats["retrieval_alignment_high_conf"]),
                "retrieval_alignment_low_conf": bool(feats["retrieval_alignment_low_conf"]),
            },
        }
        enriched["features_stage3_1"] = feats
        out_records.append(enriched)

    with open(os.path.join(OUT, "alignment_feature_dataset.jsonl"), "w") as f:
        for rec in out_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    json.dump(out_records, open(os.path.join(OUT, "alignment_feature_dataset.json"), "w"), indent=2, ensure_ascii=False)
    summary = summarize_alignment(out_records)
    json.dump(summary, open(os.path.join(OUT, "alignment_feature_quality.json"), "w"), indent=2, ensure_ascii=False)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    build()
