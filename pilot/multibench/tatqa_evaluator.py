"""TAT-QA official-compatible evaluation wrapper.

This module wraps the official TAT-QA `TaTQAEmAndF1` implementation vendored in
`pilot/multibench/official_tatqa/`. It does not define a new metric.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OFFICIAL_DIR = os.path.join(os.path.dirname(__file__), "official_tatqa")
if OFFICIAL_DIR not in sys.path:
    sys.path.insert(0, OFFICIAL_DIR)

from tatqa_metric import TaTQAEmAndF1, get_answer_str, get_metrics  # noqa: E402

RAW_DIR = os.path.join(ROOT, "data", "tatqa", "raw")
OUT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "tatqa")


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def raw_path(split: str) -> str:
    return os.path.join(RAW_DIR, f"tatqa_dataset_{split}.json")


def iter_gold_questions(gold_contexts: list[dict[str, Any]]):
    for context in gold_contexts:
        for qa in context.get("questions", []):
            if "answer" in qa:
                yield qa


def normalize_prediction_value(value: Any) -> Any:
    """Keep official semantics while tolerating project-level prediction records."""
    if isinstance(value, dict):
        if "answer" in value:
            return normalize_prediction_value(value["answer"])
        if "prediction" in value:
            return normalize_prediction_value(value["prediction"])
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return [str(v) if isinstance(v, (int, float)) else v for v in value]
    return value


def normalize_prediction_scale(value: Any, fallback: str = "") -> str:
    if isinstance(value, dict):
        return value.get("scale", fallback) or ""
    return fallback or ""


def parse_prediction_entry(entry: Any) -> tuple[Any, str]:
    """Accept official `[answer, scale]` or a dict with `answer`/`scale`."""
    if isinstance(entry, list) and len(entry) == 2:
        return normalize_prediction_value(entry[0]), entry[1] or ""
    if isinstance(entry, tuple) and len(entry) == 2:
        return normalize_prediction_value(entry[0]), entry[1] or ""
    if isinstance(entry, dict):
        return normalize_prediction_value(entry), normalize_prediction_scale(entry)
    return entry, ""


def evaluate_contexts(gold_contexts: list[dict[str, Any]], predictions: dict[str, Any]) -> dict[str, Any]:
    metric = TaTQAEmAndF1()
    missing = []
    details = []
    for qa in iter_gold_questions(gold_contexts):
        qid = qa["uid"]
        pred_answer, pred_scale = None, None
        if qid in predictions:
            pred_answer, pred_scale = parse_prediction_entry(predictions[qid])
        else:
            missing.append(qid)
        metric(ground_truth=qa, prediction=pred_answer, pred_scale=pred_scale)
    em, f1, scale_score, op_score = metric.get_overall_metric()
    raw_details = metric.get_raw()
    by_answer_type = defaultdict(lambda: {"count": 0, "em_sum": 0.0, "f1_sum": 0.0})
    by_scale = defaultdict(lambda: {"count": 0, "em_sum": 0.0, "f1_sum": 0.0})
    for d in raw_details:
        at = d.get("answer_type", "missing")
        scale = d.get("scale", "")
        by_answer_type[at]["count"] += 1
        by_answer_type[at]["em_sum"] += float(d.get("em", 0.0))
        by_answer_type[at]["f1_sum"] += float(d.get("f1", 0.0))
        by_scale[scale]["count"] += 1
        by_scale[scale]["em_sum"] += float(d.get("em", 0.0))
        by_scale[scale]["f1_sum"] += float(d.get("f1", 0.0))
        details.append({
            "uid": d.get("uid"),
            "answer_type": at,
            "scale": scale,
            "answer": d.get("answer"),
            "pred": d.get("pred"),
            "pred_scale": d.get("pred_scale"),
            "em": d.get("em"),
            "f1": d.get("f1"),
        })

    def finalize(grouped):
        return {
            k: {
                "count": v["count"],
                "em": v["em_sum"] / v["count"] if v["count"] else 0.0,
                "f1": v["f1_sum"] / v["count"] if v["count"] else 0.0,
            }
            for k, v in sorted(grouped.items())
        }

    return {
        "count": len(raw_details),
        "missing_predictions": len(missing),
        "exact_match": em,
        "f1": f1,
        "scale_score": scale_score,
        "op_score": op_score,
        "by_answer_type": finalize(by_answer_type),
        "by_scale": finalize(by_scale),
        "missing_prediction_uids": missing[:20],
        "details": details,
    }


def build_gold_predictions(gold_contexts: list[dict[str, Any]]) -> dict[str, list[Any]]:
    """Create official-format predictions directly from gold answer+scale."""
    return {
        qa["uid"]: [normalize_prediction_value(qa["answer"]), qa.get("scale", "")]
        for qa in iter_gold_questions(gold_contexts)
    }


def self_check_split(split: str) -> dict[str, Any]:
    gold = load_json(raw_path(split))
    predictions = build_gold_predictions(gold)
    result = evaluate_contexts(gold, predictions)
    failures = [
        d for d in result["details"]
        if float(d["em"]) != 1.0 or float(d["f1"]) != 1.0 or (d.get("pred_scale") or "") != (d.get("scale") or "")
    ]
    result["gold_prediction_failures"] = len(failures)
    result["gold_prediction_failure_examples"] = failures[:20]
    result.pop("details")
    return result


def self_check(splits: list[str]) -> dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True)
    out = {"splits": {}, "source": "official TAT-QA TaTQAEmAndF1"}
    for split in splits:
        out["splits"][split] = self_check_split(split)
    with open(os.path.join(OUT_DIR, "tatqa_evaluator_self_check.json"), "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    return out


def evaluate_prediction_file(gold_path: str, pred_path: str) -> dict[str, Any]:
    gold = load_json(gold_path)
    pred = load_json(pred_path)
    return evaluate_contexts(gold, pred)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-path")
    parser.add_argument("--pred-path")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--splits", nargs="+", default=["train", "dev"])
    parser.add_argument("--out")
    args = parser.parse_args()

    if args.self_check:
        result = self_check(args.splits)
    else:
        if not args.gold_path or not args.pred_path:
            raise SystemExit("--gold-path and --pred-path are required unless --self-check is used")
        result = evaluate_prediction_file(args.gold_path, args.pred_path)

    if args.out:
        with open(args.out, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    print(json.dumps({
        "splits": {
            k: {
                "count": v["count"],
                "em": v["exact_match"],
                "f1": v["f1"],
                "scale": v["scale_score"],
                "gold_prediction_failures": v.get("gold_prediction_failures"),
            }
            for k, v in result.get("splits", {}).items()
        } if "splits" in result else None,
        "count": result.get("count"),
        "em": result.get("exact_match"),
        "f1": result.get("f1"),
        "scale": result.get("scale_score"),
    }, indent=2))


if __name__ == "__main__":
    main()
