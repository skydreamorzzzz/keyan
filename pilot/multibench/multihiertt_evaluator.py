"""MultiHiertt official-compatible evaluation wrapper.

The scorer reuses the official MultiHiertt evaluation semantics vendored under
`pilot/multibench/official_multihiertt/`. It does not build memory, retrieve,
run prompts, or define a new metric.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict
from typing import Any

import pyarrow.parquet as pq

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pilot.multibench.official_multihiertt.evaluate import (
    evaluate_program_result,
    evaluate_span_program_result,
)
from pilot.multibench.official_multihiertt.utils.program_generation_utils import (
    eval_program,
    program_tokenization,
)
from pilot.multibench.official_multihiertt.utils.span_selection_utils import get_span_selection_metrics
from pilot.multibench.official_multihiertt.utils.utils import str_to_num

RAW_DIR = os.path.join(ROOT, "data", "multihiertt", "raw")
OUT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "multihiertt")
SELF_CHECK_PATH = os.path.join(OUT_DIR, "multihiertt_evaluator_self_check.json")
AUDIT_MD_PATH = os.path.join(OUT_DIR, "MULTIHIERTT_EVALUATOR_AUDIT.md")


def load_parquet_rows(split: str) -> list[dict[str, Any]]:
    return pq.read_table(os.path.join(RAW_DIR, f"{split}.parquet")).to_pylist()


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def prediction_answer(entry: Any) -> Any:
    if isinstance(entry, dict):
        for key in ("predicted_ans", "predicted_answer", "answer", "prediction"):
            if key in entry:
                return entry[key]
    return entry


def prediction_program(entry: Any) -> Any:
    if isinstance(entry, dict):
        for key in ("predicted_program", "program", "pred_program"):
            if key in entry:
                return entry[key]
    return None


def normalize_span_value(value: Any) -> Any:
    """Compatibility only: cast numeric/list members to strings for official span metric."""
    if isinstance(value, list):
        return [str(v) if isinstance(v, (int, float)) else v for v in value]
    if isinstance(value, (int, float)):
        return str(value)
    return value


def normalize_program_value(value: Any) -> list[str] | None:
    """Compatibility only: accept official token-list or raw program string."""
    if not value:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return program_tokenization(value)
    return None


def official_numeric_close(pred_answer: Any, gold_number: float) -> tuple[float, float]:
    """Use the official mixed span/program tolerance for answer-only numeric predictions."""
    pred_num = str_to_num(str(pred_answer))
    if pred_num == "n/a":
        return get_span_selection_metrics(str(pred_answer), str(gold_number))
    if math.isclose(float(pred_num), float(gold_number), abs_tol=min(abs(min(float(pred_num), gold_number) / 1000), 0.1)):
        return 1.0, 1.0
    return 0.0, 0.0


def evaluate_one(gold: dict[str, Any], prediction: Any) -> dict[str, Any]:
    gold_program = gold.get("program") or ""
    gold_answer = gold.get("answer")
    pred_program = normalize_program_value(prediction_program(prediction))
    pred_answer = normalize_span_value(prediction_answer(prediction))
    answer_type = "program" if gold_program else "span"
    eval_mode = None
    invalid_program = False
    if gold_program:
        if pred_program:
            em, f1 = evaluate_program_result(pred_program, gold_program)
            eval_mode = "program_vs_program"
        else:
            invalid, gold_exe = eval_program(program_tokenization(gold_program))
            invalid_program = bool(invalid)
            if invalid:
                em, f1 = 0.0, 0.0
            else:
                em, f1 = official_numeric_close(pred_answer, float(gold_exe))
            eval_mode = "answer_vs_gold_program_execution"
    else:
        if pred_program:
            invalid, pred_exe = eval_program(pred_program)
            invalid_program = bool(invalid)
            if invalid:
                em, f1 = 0.0, 0.0
            else:
                em, f1 = evaluate_span_program_result(span_ans=gold_answer, prog_ans=float(pred_exe))
            eval_mode = "program_execution_vs_span"
        else:
            em, f1 = get_span_selection_metrics(pred_answer, gold_answer)
            eval_mode = "span_vs_span"
    return {
        "uid": gold.get("uid"),
        "answer_type": answer_type,
        "gold_answer": gold_answer,
        "gold_program": gold_program,
        "pred_answer": pred_answer,
        "pred_program": pred_program,
        "eval_mode": eval_mode,
        "invalid_program": invalid_program,
        "em": float(em),
        "f1": float(f1),
    }


def evaluate_rows(rows: list[dict[str, Any]], predictions: dict[str, Any]) -> dict[str, Any]:
    details = []
    missing = []
    for row in rows:
        uid = row["uid"]
        if uid not in predictions:
            missing.append(uid)
            pred = None
        else:
            pred = predictions[uid]
        details.append(evaluate_one(row, pred))
    em = sum(d["em"] for d in details) / len(details) if details else 0.0
    f1 = sum(d["f1"] for d in details) / len(details) if details else 0.0
    by_type = defaultdict(lambda: {"count": 0, "em_sum": 0.0, "f1_sum": 0.0})
    by_mode = Counter()
    invalid_programs = 0
    for d in details:
        group = by_type[d["answer_type"]]
        group["count"] += 1
        group["em_sum"] += d["em"]
        group["f1_sum"] += d["f1"]
        by_mode[d["eval_mode"]] += 1
        invalid_programs += int(d["invalid_program"])
    return {
        "count": len(details),
        "missing_predictions": len(missing),
        "exact_match": em,
        "f1": f1,
        "invalid_programs": invalid_programs,
        "eval_mode_counts": dict(by_mode),
        "by_answer_type": {
            key: {
                "count": value["count"],
                "exact_match": value["em_sum"] / value["count"] if value["count"] else 0.0,
                "f1": value["f1_sum"] / value["count"] if value["count"] else 0.0,
            }
            for key, value in sorted(by_type.items())
        },
        "missing_prediction_uids": missing[:20],
        "details": details,
    }


def gold_predictions(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    preds = {}
    for row in rows:
        if row.get("program"):
            preds[row["uid"]] = {"predicted_program": row["program"], "predicted_ans": row["answer"]}
        else:
            preds[row["uid"]] = {"predicted_ans": row["answer"], "predicted_program": ""}
    return preds


def self_check_split(split: str) -> dict[str, Any]:
    rows = load_parquet_rows(split)
    result = evaluate_rows(rows, gold_predictions(rows))
    failures = [d for d in result["details"] if d["em"] != 1.0 or d["f1"] != 1.0]
    result["gold_prediction_failures"] = len(failures)
    result["gold_prediction_failure_examples"] = failures[:20]
    result.pop("details")
    return result


def run_self_check(splits: list[str]) -> dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True)
    result = {
        "source": {
            "official_repository": "https://github.com/psunlpgroup/MultiHiertt",
            "official_evaluate_py": "https://github.com/psunlpgroup/MultiHiertt/blob/main/evaluate.py",
            "vendored_subset": "pilot/multibench/official_multihiertt/",
        },
        "compatibility_normalization": [
            "Prediction dicts may use predicted_ans/predicted_answer/answer/prediction for answer text.",
            "Prediction dicts may use predicted_program/program/pred_program for program text.",
            "Raw program strings are tokenized with official program_tokenization before official execution.",
            "Numeric/list prediction values are cast to strings only before official span metric.",
            "Official str_to_num semantics are preserved, including removing $, comma, percent sign, and hyphen.",
            "Answer-only predictions for program gold are compared to official gold program execution using official mixed span/program numeric tolerance.",
        ],
        "splits": {split: self_check_split(split) for split in splits},
    }
    write_json(SELF_CHECK_PATH, result)
    write_report(result)
    return result


def write_report(result: dict[str, Any]) -> None:
    lines = [
        "# MultiHiertt Evaluator Audit",
        "",
        "Date: 2026-08-17",
        "",
        "Scope: official-compatible evaluator only. No LLM/API calls, memory construction, retrieval, four-arm experiment, or prompt execution.",
        "",
        "## Source / Compatibility",
        "",
        "- Official reference: `psunlpgroup/MultiHiertt/evaluate.py`.",
        "- Project wrapper: `pilot/multibench/multihiertt_evaluator.py`.",
        "- Vendored official subset: `pilot/multibench/official_multihiertt/`.",
        "- The wrapper delegates span scoring, program tokenization, program execution, and mixed span/program numerical tolerance to official-compatible functions.",
        "",
        "## Compatibility Normalization",
        "",
    ]
    lines.extend(f"- {item}" for item in result["compatibility_normalization"])
    lines.extend([
        "",
        "Important official semantics retained: `str_to_num` strips `$`, `,`, `%`, and `-`. This means negative signs are not distinguished by the official numeric parser; this is recorded as a compatibility risk rather than silently corrected.",
        "",
        "## Gold Prediction Self-Check",
        "",
        "| Split | Count | EM | F1 | Program | Span | Invalid programs | Gold failures |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for split, summary in result["splits"].items():
        by_type = summary["by_answer_type"]
        lines.append(
            f"| `{split}` | {summary['count']} | {summary['exact_match']:.3f} | {summary['f1']:.3f} | "
            f"{by_type.get('program', {}).get('count', 0)} | {by_type.get('span', {}).get('count', 0)} | "
            f"{summary['invalid_programs']} | {summary['gold_prediction_failures']} |"
        )
    lines.extend([
        "",
        "## Unit Test Coverage",
        "",
        "- Program execution: add/subtract/divide tokenized program equality.",
        "- Numeric normalization: currency/comma/percent behavior inherited from official `str_to_num`.",
        "- Negative-number compatibility risk: official parser removes hyphen.",
        "- Span and multi-span exact/F1 behavior.",
        "",
        "## Decision",
        "",
    ])
    failures = sum(s["gold_prediction_failures"] for s in result["splits"].values())
    decision = "EVALUATOR FROZEN" if failures == 0 else "FIX EVALUATOR FIRST"
    lines.append(f"Decision: `{decision}`.")
    with open(AUDIT_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def evaluate_prediction_file(split: str, pred_path: str) -> dict[str, Any]:
    rows = load_parquet_rows(split)
    predictions = load_json(pred_path)
    return evaluate_rows(rows, predictions)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--splits", nargs="+", default=["validation"])
    parser.add_argument("--split", default="validation")
    parser.add_argument("--pred-path")
    parser.add_argument("--out")
    args = parser.parse_args()

    if args.self_check:
        result = run_self_check(args.splits)
    else:
        if not args.pred_path:
            raise SystemExit("--pred-path is required unless --self-check is used")
        result = evaluate_prediction_file(args.split, args.pred_path)
    if args.out:
        write_json(args.out, result)
    print(json.dumps({
        "splits": {
            split: {
                "count": summary["count"],
                "em": summary["exact_match"],
                "f1": summary["f1"],
                "gold_prediction_failures": summary.get("gold_prediction_failures"),
            }
            for split, summary in result.get("splits", {}).items()
        } if "splits" in result else None,
        "count": result.get("count"),
        "em": result.get("exact_match"),
        "f1": result.get("f1"),
    }, indent=2))


if __name__ == "__main__":
    main()
