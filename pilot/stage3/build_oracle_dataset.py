"""Build per-query oracle analysis data for Stage 3.

The output intentionally separates inference-time-safe `features` from
gold/correctness `labels` and `analysis` fields.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from collections import Counter
from typing import Any

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PILOT = os.path.join(ROOT, "pilot")
if PILOT not in sys.path:
    sys.path.insert(0, PILOT)
if os.path.join(PILOT, "stage2_official") not in sys.path:
    sys.path.insert(0, os.path.join(PILOT, "stage2_official"))

import finqa_common as fc  # noqa: E402
import retrieval  # noqa: E402
import s2o_common as c  # noqa: E402
from executor import exec_program_re, match_result  # noqa: E402

OUT = os.path.join(PILOT, "stage3")
N = 492
TOP_CASE = 4
TOP_STRATEGY = 3
ARMS = {
    "none": "baseline",
    "case": "baseline_case",
    "strategy": "baseline_strategy",
    "both": "baseline_both",
}
STRUCT_ARMS = {
    "none": "structured",
    "case": "structured_case",
    "strategy": "structured_strategy",
    "both": "structured_both",
}


def load_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def ratio(num: float, den: float) -> float:
    return float(num / den) if den else 0.0


def entropy(values: list[str]) -> float:
    if not values:
        return 0.0
    counts = Counter(values)
    n = len(values)
    return -sum((v / n) * math.log(v / n + 1e-12) for v in counts.values())


def normalize_struct(struct: list[str] | tuple[str, ...] | None) -> str:
    if not struct:
        return ""
    return ">".join(str(x) for x in struct)


def op_family_from_ops(ops: list[str]) -> str:
    if any(o == "greater" for o in ops):
        return "comparison"
    if any(o.startswith("table_") for o in ops):
        return "table_aggregation"
    if any(o in ("divide",) for o in ops) and any(o in ("subtract",) for o in ops):
        return "change"
    if any(o == "divide" for o in ops):
        return "ratio"
    if any(o in ("add", "table_sum") for o in ops):
        return "aggregation"
    if any(o == "multiply" for o in ops):
        return "scaling"
    return "other"


def infer_query_family(q: str) -> dict[str, Any]:
    ql = q.lower()
    flags = {
        "asks_percent": int(any(x in ql for x in ["percent", "percentage", "%"])),
        "asks_ratio": int(any(x in ql for x in ["ratio", "portion", "share", "per ", "margin"])),
        "asks_change": int(any(x in ql for x in ["change", "increase", "decrease", "growth", "decline", "difference"])),
        "asks_average": int(any(x in ql for x in ["average", "mean"])),
        "asks_sum": int(any(x in ql for x in ["total", "sum", "combined"])),
        "asks_compare": int(any(x in ql for x in ["greater", "higher", "less", "lower", "more than", "compared"])),
        "asks_maxmin": int(any(x in ql for x in ["maximum", "minimum", "largest", "smallest", "highest", "lowest"])),
    }
    if flags["asks_compare"]:
        fam = "comparison"
    elif flags["asks_average"] or flags["asks_maxmin"]:
        fam = "table_aggregation"
    elif flags["asks_change"]:
        fam = "change"
    elif flags["asks_ratio"] or flags["asks_percent"]:
        fam = "ratio"
    elif flags["asks_sum"]:
        fam = "aggregation"
    else:
        fam = "other"
    years = re.findall(r"\b(?:19|20)\d{2}\b", q)
    nums = re.findall(r"[-+]?\d+(?:\.\d+)?%?", q)
    return {
        **flags,
        "query_operation_family": fam,
        "question_len_tokens": len(re.findall(r"[A-Za-z0-9_%.-]+", q)),
        "question_num_count": len(nums),
        "question_year_count": len(years),
        "question_unique_year_count": len(set(years)),
        "question_has_unit_word": int(any(x in ql for x in ["million", "billion", "thousand", "dollar", "$"])),
        "question_has_scale_word": int(any(x in ql for x in ["million", "billion", "thousand"])),
    }


def score_stats(rows: list[dict[str, Any]], key: str = "score") -> dict[str, float]:
    vals = [float(r.get(key, 0.0)) for r in rows]
    vals = vals + [0.0] * max(0, 4 - len(vals))
    top = vals[0] if vals else 0.0
    second = vals[1] if len(vals) > 1 else 0.0
    return {
        "top": top,
        "second": second,
        "mean": float(np.mean(vals)) if vals else 0.0,
        "std": float(np.std(vals)) if vals else 0.0,
        "margin": top - second,
    }


def ff_correct(outs: dict[str, Any], dev: list[dict[str, Any]], arm: str, i: int) -> bool:
    raw = outs["ff"].get(arm, {}).get(str(i), "")
    return bool(c.numeric_close(raw, dev[i]["qa"].get("answer", ""), dev[i]["qa"]["question"]))


def prog_correct(outs: dict[str, Any], dev: list[dict[str, Any]], arm: str, i: int) -> bool:
    raw = outs["prog"].get(arm, {}).get(str(i), "")
    ok, res = exec_program_re(raw, dev[i]["table"])
    return bool(ok and match_result(res, dev[i]["qa"]["exe_ans"]))


def arm_label(correct: dict[str, bool], arm_priors: dict[str, float] | None = None) -> str:
    ok = [a for a in ["none", "case", "strategy", "both"] if correct[a]]
    if not ok:
        return "none"
    if arm_priors:
        return max(ok, key=lambda a: (arm_priors.get(a, 0.0), a == "both"))
    return ok[0]


def build() -> None:
    os.makedirs(OUT, exist_ok=True)
    dev = load_json(os.path.join(ROOT, "data", "finqa", "dev.json"))[:N]
    outs = load_json(os.path.join(PILOT, "stage2_official", "output", "arm_outputs.json"))
    cases = {x["case_id"]: x for x in load_json(os.path.join(PILOT, "output", "case_memory.json"))}
    strats = {x["strategy_id"]: x for x in load_json(os.path.join(PILOT, "output", "strategies_clean.json"))}
    case_emb, case_order = retrieval.load_case_index()
    strat_emb, strat_order = retrieval.load_strategy_index()
    case_pos = {cid: j for j, cid in enumerate(case_order)}
    strat_pos = {sid: j for j, sid in enumerate(strat_order)}

    records: list[dict[str, Any]] = []
    retrieval._load_meta()

    for i, ex in enumerate(dev):
        q = ex["qa"]["question"]
        cat = fc.compute_cat(ex)
        gold_ops = cat["ops"]
        gold_struct = normalize_struct(cat["struct"])
        gold_bucket = fc.bucket(cat)
        qfam = infer_query_family(q)

        rc = retrieval.retrieve_cases(q, TOP_CASE)
        rs = retrieval.retrieve_strategies_v2(q, TOP_STRATEGY)
        cstats = score_stats(rc)
        sstats = score_stats(rs)

        case_items = []
        for rank, r in enumerate(rc, 1):
            cm = cases[r["case_id"]]
            cstruct = normalize_struct(cm.get("struct"))
            case_items.append({
                "rank": rank,
                "case_id": r["case_id"],
                "score": r["score"],
                "problem_kind": cm.get("problem_kind"),
                "n_steps": cm.get("n_steps"),
                "struct": cm.get("struct"),
                "operation_family": op_family_from_ops(cm.get("struct", [])),
                "same_gold_struct": cstruct == gold_struct,
                "question": cm.get("question"),
                "exe_ans": cm.get("exe_ans"),
            })

        strategy_items = []
        for rank, r in enumerate(rs, 1):
            sm = strats[r["strategy_id"]]
            fams = [normalize_struct(x) for x in sm.get("program_family", [])]
            strategy_items.append({
                "rank": rank,
                "strategy_id": r["strategy_id"],
                "score": r["score"],
                "case_hits": r.get("case_hits", 0),
                "name": sm.get("name"),
                "problem_pattern": sm.get("problem_pattern"),
                "canonical_output_scale": sm.get("canonical_output_scale"),
                "program_family": sm.get("program_family"),
                "matches_gold_struct": gold_struct in fams,
            })

        case_fams = [x["operation_family"] for x in case_items]
        strat_fams = [op_family_from_ops(fam) for s in strategy_items for fam in s["program_family"]]
        top_case_structs = {normalize_struct(x["struct"]) for x in case_items}
        top_strat_structs = {normalize_struct(f) for s in strategy_items for f in s["program_family"]}
        case_strat_struct_overlap = len(top_case_structs & top_strat_structs)

        full_prog = {name: prog_correct(outs, dev, arm, i) for name, arm in ARMS.items()}
        structured_prog = {name: prog_correct(outs, dev, arm, i) for name, arm in STRUCT_ARMS.items()}
        full_ff = {name: ff_correct(outs, dev, arm, i) for name, arm in ARMS.items()}
        structured_ff = {name: ff_correct(outs, dev, arm, i) for name, arm in STRUCT_ARMS.items()}

        case_vecs = [case_emb[case_pos[r["case_id"]]] for r in rc if r["case_id"] in case_pos]
        strat_vecs = [strat_emb[strat_pos[r["strategy_id"]]] for r in rs if r["strategy_id"] in strat_pos]
        retrieved_repr = {}
        if case_vecs:
            cv = np.mean(np.stack(case_vecs), axis=0)
            for j, val in enumerate(cv[:64]):
                retrieved_repr[f"case_emb64_{j:02d}"] = float(val)
        if strat_vecs:
            sv = np.mean(np.stack(strat_vecs), axis=0)
            for j, val in enumerate(sv[:64]):
                retrieved_repr[f"strategy_emb64_{j:02d}"] = float(val)

        safe_features = {
            **{k: v for k, v in qfam.items() if k != "query_operation_family"},
            "query_family_" + qfam["query_operation_family"]: 1,
            "case_top_score": cstats["top"],
            "case_second_score": cstats["second"],
            "case_score_mean": cstats["mean"],
            "case_score_std": cstats["std"],
            "case_score_margin": cstats["margin"],
            "case_top_n_steps": float(case_items[0]["n_steps"] or 0) if case_items else 0.0,
            "case_mean_n_steps": float(np.mean([x["n_steps"] or 0 for x in case_items])) if case_items else 0.0,
            "case_family_entropy": entropy(case_fams),
            "case_top_family_matches_query": int(bool(case_items) and case_items[0]["operation_family"] == qfam["query_operation_family"]),
            "strategy_top_score": sstats["top"],
            "strategy_second_score": sstats["second"],
            "strategy_score_mean": sstats["mean"],
            "strategy_score_std": sstats["std"],
            "strategy_score_margin": sstats["margin"],
            "strategy_top_case_hits": float(rs[0].get("case_hits", 0) if rs else 0),
            "strategy_mean_case_hits": float(np.mean([r.get("case_hits", 0) for r in rs])) if rs else 0.0,
            "strategy_family_entropy": entropy(strat_fams),
            "strategy_any_family_matches_query": int(qfam["query_operation_family"] in set(strat_fams)),
            "case_strategy_score_gap": cstats["top"] - sstats["top"],
            "case_strategy_struct_overlap": float(case_strat_struct_overlap),
            "case_strategy_top_family_agree": int(bool(case_fams and strat_fams) and case_fams[0] == strat_fams[0]),
            "both_retrieval_high": int(cstats["top"] >= 0.55 and sstats["top"] >= 0.55),
            "retrieval_confidence_disagreement": abs(cstats["top"] - sstats["top"]),
            **retrieved_repr,
        }

        rec = {
            "sample_index": i,
            "sample_id": ex.get("id", str(i)),
            "filename": ex.get("filename"),
            "question": q,
            "features": safe_features,
            "retrieval": {
                "case": case_items,
                "strategy": strategy_items,
                "case_top_score": cstats["top"],
                "case_margin": cstats["margin"],
                "strategy_top_score": sstats["top"],
                "strategy_margin": sstats["margin"],
                "case_strategy_struct_overlap": case_strat_struct_overlap,
            },
            "analysis": {
                "gold_problem_family": gold_bucket,
                "gold_operation_family": op_family_from_ops(gold_ops),
                "gold_n_steps": cat["nstep"],
                "gold_struct": cat["struct"],
                "uses_table_op": cat["uses_table_op"],
                "uses_greater": cat["uses_greater"],
                "uses_const": cat["uses_const"],
                "num_text_gold_facts": cat["num_text"],
                "num_table_gold_facts": cat["num_table"],
                "unit_percent_scale": {
                    "gold_answer_has_percent": "%" in str(ex["qa"].get("answer", "")),
                    "question_percent": bool(qfam["asks_percent"]),
                    "question_scale_word": bool(qfam["question_has_scale_word"]),
                    "program_uses_const": cat["uses_const"],
                },
                "case_family_consistency_gold": {
                    "top1_same_struct": bool(case_items and case_items[0]["same_gold_struct"]),
                    "any_same_struct": any(x["same_gold_struct"] for x in case_items),
                    "same_struct_count": sum(x["same_gold_struct"] for x in case_items),
                },
                "strategy_family_consistency_gold": {
                    "top1_matches": bool(strategy_items and strategy_items[0]["matches_gold_struct"]),
                    "any_matches": any(x["matches_gold_struct"] for x in strategy_items),
                    "matches_count": sum(x["matches_gold_struct"] for x in strategy_items),
                },
            },
            "labels": {
                "full_doc_prog_correct": full_prog,
                "structured_prog_correct": structured_prog,
                "full_doc_ff_correct": full_ff,
                "structured_ff_correct": structured_ff,
                "full_doc_prog_correct_arms": [a for a, ok in full_prog.items() if ok],
                "structured_prog_correct_arms": [a for a, ok in structured_prog.items() if ok],
                "full_doc_prog_oracle_set": [a for a, ok in full_prog.items() if ok],
                "structured_prog_oracle_set": [a for a, ok in structured_prog.items() if ok],
            },
        }
        records.append(rec)

    # Deterministic preferred labels for classifiers, using fixed-arm full-data priors
    priors = {a: ratio(sum(r["labels"]["full_doc_prog_correct"][a] for r in records), len(records)) for a in ARMS}
    for rec in records:
        rec["labels"]["full_doc_prog_preferred_arm"] = arm_label(rec["labels"]["full_doc_prog_correct"], priors)
        rec["labels"]["structured_prog_preferred_arm"] = arm_label(rec["labels"]["structured_prog_correct"])

    json.dump(records, open(os.path.join(OUT, "oracle_analysis_dataset.json"), "w"), indent=2, ensure_ascii=False)
    with open(os.path.join(OUT, "oracle_analysis_dataset.jsonl"), "w") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"wrote {len(records)} records to {OUT}")


if __name__ == "__main__":
    build()
