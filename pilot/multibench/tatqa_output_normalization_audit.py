"""TAT-QA output normalization audit over frozen four-arm raw outputs.

No LLM/API calls. This script re-evaluates the existing 30 x 4 cached dry-run
outputs with and without conservative prediction canonicalization.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if os.path.join(ROOT, "pilot") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "pilot"))
if os.path.dirname(__file__) not in sys.path:
    sys.path.insert(0, os.path.dirname(__file__))

from tatqa_evaluator import evaluate_contexts, raw_path  # noqa: E402
from tatqa_four_arm_dry_run import ARMS  # noqa: E402

OUT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "tatqa")
FOUR_ARM_JSON_PATH = os.path.join(OUT_DIR, "tatqa_four_arm_dry_run.json")
AUDIT_JSON_PATH = os.path.join(OUT_DIR, "tatqa_output_normalization_audit.json")
REPORT_PATH = os.path.join(OUT_DIR, "TATQA_OUTPUT_NORMALIZATION_AUDIT.md")

SCALE_ALIASES = {
    "": "",
    "none": "",
    "thousand": "thousand",
    "thousands": "thousand",
    "million": "million",
    "millions": "million",
    "billion": "billion",
    "billions": "billion",
    "percent": "percent",
    "percentage": "percent",
    "%": "percent",
}
SCALE_WORD_PATTERN = r"(?:thousands?|millions?|billions?|percent(?:age)?|%)"
NUMERIC_WITH_OPTIONAL_SCALE = re.compile(
    rf"^\s*[\$€£¥]?\s*([+-]?(?:\d{{1,3}}(?:,\d{{3}})+|\d+)(?:\.\d+)?|[+-]?\.\d+)\s*({SCALE_WORD_PATTERN})?\s*$",
    re.I,
)


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def canonical_scale(scale: Any) -> str:
    s = "" if scale is None else str(scale).strip().lower()
    return SCALE_ALIASES.get(s, s)


def clean_number_text(num: str) -> str:
    num = num.replace(",", "")
    if num.startswith("+"):
        num = num[1:]
    return num


def canonicalize_scalar_answer(answer: Any, scale: Any) -> tuple[Any, str, list[str]]:
    """Conservatively canonicalize a single prediction answer.

    Only pure numeric/currency strings with an optional scale token are changed.
    Textual spans containing words are left untouched.
    """
    pred_scale = canonical_scale(scale)
    changes: list[str] = []
    if isinstance(answer, (int, float)):
        return answer, pred_scale, changes
    if answer is None:
        return answer, pred_scale, changes
    text = " ".join(str(answer).strip().split())
    m = NUMERIC_WITH_OPTIONAL_SCALE.match(text)
    if not m:
        return answer, pred_scale, changes
    number = clean_number_text(m.group(1))
    embedded_scale = canonical_scale(m.group(2) or "")
    if number != text:
        changes.append("numeric_format")
    if embedded_scale:
        changes.append(f"embedded_scale:{embedded_scale}")
        if not pred_scale:
            pred_scale = embedded_scale
            changes.append("scale_split")
        elif pred_scale == embedded_scale:
            changes.append("duplicate_scale_removed")
        else:
            changes.append(f"scale_conflict:{embedded_scale}->{pred_scale}")
    if embedded_scale == "percent" and pred_scale == "percent":
        # Official TAT-QA treats a percent sign in the answer specially and avoids
        # applying pred_scale twice. Keep the percent marker, normalize the word.
        return f"{number}%", pred_scale, changes
    return number, pred_scale, changes


def canonicalize_prediction(prediction: dict[str, Any] | None) -> tuple[dict[str, Any] | None, list[str]]:
    if prediction is None:
        return None, []
    answer = prediction.get("answer")
    scale = prediction.get("scale", "")
    changes: list[str] = []
    if isinstance(answer, list):
        new_answer = []
        new_scale = canonical_scale(scale)
        for item in answer:
            c_item, c_scale, c_changes = canonicalize_scalar_answer(item, new_scale)
            new_answer.append(c_item)
            if c_scale != new_scale:
                new_scale = c_scale
            changes.extend(c_changes)
        return {"answer": new_answer, "scale": new_scale}, sorted(set(changes))
    c_answer, c_scale, changes = canonicalize_scalar_answer(answer, scale)
    return {"answer": c_answer, "scale": c_scale}, sorted(set(changes))


def subset_gold_contexts(uids: set[str]) -> list[dict[str, Any]]:
    raw = load_json(raw_path("dev"))
    out = []
    for ctx in raw:
        qs = [q for q in ctx.get("questions", []) if q.get("uid") in uids]
        if qs:
            c = dict(ctx)
            c["questions"] = qs
            out.append(c)
    return out


def predictions_from_records(records: list[dict[str, Any]], arm: str, canonicalized: bool) -> tuple[dict[str, Any], dict[str, list[str]]]:
    predictions = {}
    changes = {}
    for rec in records:
        parsed = rec["outputs"][arm]["parsed"]
        if canonicalized:
            parsed, change_tags = canonicalize_prediction(parsed)
            changes[rec["uid"]] = change_tags
        if parsed is None:
            predictions[rec["uid"]] = [None, ""]
        else:
            predictions[rec["uid"]] = [parsed.get("answer"), parsed.get("scale", "")]
    return predictions, changes


def evaluate_with_details(gold_contexts: list[dict[str, Any]], predictions: dict[str, Any]) -> dict[str, Any]:
    result = evaluate_contexts(gold_contexts, predictions)
    return result


def event_counts(records: list[dict[str, Any]], details_by_arm: dict[str, dict[str, dict[str, Any]]]) -> dict[str, int]:
    arm_correct = {
        arm: {rec["sample_id"] for rec in records if float(details_by_arm[arm][rec["uid"]]["em"]) == 1.0}
        for arm in ARMS
    }
    return {
        "case_only": len(arm_correct["case"] - arm_correct["none"] - arm_correct["strategy"] - arm_correct["both"]),
        "strategy_only": len(arm_correct["strategy"] - arm_correct["none"] - arm_correct["case"] - arm_correct["both"]),
        "none_only": len(arm_correct["none"] - arm_correct["case"] - arm_correct["strategy"] - arm_correct["both"]),
        "both_only": len(arm_correct["both"] - arm_correct["none"] - arm_correct["case"] - arm_correct["strategy"]),
        "none_gt_both": sum(float(details_by_arm["none"][rec["uid"]]["em"]) > float(details_by_arm["both"][rec["uid"]]["em"]) for rec in records),
        "case_gt_both": sum(float(details_by_arm["case"][rec["uid"]]["em"]) > float(details_by_arm["both"][rec["uid"]]["em"]) for rec in records),
        "strategy_gt_both": sum(float(details_by_arm["strategy"][rec["uid"]]["em"]) > float(details_by_arm["both"][rec["uid"]]["em"]) for rec in records),
    }


def run() -> dict[str, Any]:
    four = load_json(FOUR_ARM_JSON_PATH)
    records = four["records"]
    gold_contexts = subset_gold_contexts({r["uid"] for r in records})
    modes = {}
    details_by_mode = {}
    changes_by_arm = {}
    for mode, canonicalized in [("raw", False), ("canonicalized", True)]:
        modes[mode] = {}
        details_by_mode[mode] = {}
        for arm in ARMS:
            preds, changes = predictions_from_records(records, arm, canonicalized)
            if canonicalized:
                changes_by_arm[arm] = changes
            result = evaluate_with_details(gold_contexts, preds)
            details_by_mode[mode][arm] = {d["uid"]: d for d in result["details"]}
            result_no_details = dict(result)
            result_no_details.pop("details", None)
            modes[mode][arm] = result_no_details

    flips = []
    flip_counter = Counter()
    for rec in records:
        for arm in ARMS:
            raw_d = details_by_mode["raw"][arm][rec["uid"]]
            can_d = details_by_mode["canonicalized"][arm][rec["uid"]]
            raw_em = float(raw_d["em"])
            can_em = float(can_d["em"])
            raw_f1 = float(raw_d["f1"])
            can_f1 = float(can_d["f1"])
            if raw_em != can_em or raw_f1 != can_f1:
                direction = "improved" if (can_em, can_f1) > (raw_em, raw_f1) else "worsened"
                flip_counter[direction] += 1
                flips.append({
                    "sample_id": rec["sample_id"],
                    "uid": rec["uid"],
                    "arm": arm,
                    "answer_type": rec["answer_type"],
                    "gold_answer": rec["gold_answer"],
                    "gold_scale": rec["scale"],
                    "raw_prediction": rec["outputs"][arm]["parsed"],
                    "canonicalized_prediction": predictions_from_records([rec], arm, True)[0][rec["uid"]],
                    "change_tags": changes_by_arm[arm].get(rec["uid"], []),
                    "raw_em": raw_em,
                    "raw_f1": raw_f1,
                    "canonicalized_em": can_em,
                    "canonicalized_f1": can_f1,
                    "direction": direction,
                    "question": rec["question"],
                })

    change_tag_counts = Counter()
    changed_predictions = 0
    for arm_changes in changes_by_arm.values():
        for tags in arm_changes.values():
            if tags:
                changed_predictions += 1
                change_tag_counts.update(tags)

    audit = {
        "version": "tatqa_output_normalization_audit_v1",
        "source_four_arm_json": os.path.relpath(FOUR_ARM_JSON_PATH, ROOT),
        "sample_n": len(records),
        "arms": ARMS,
        "normalization_contract": [
            "Strip currency symbols and comma separators only from pure numeric predictions.",
            "Split embedded thousand/million/billion/percent scale tokens from pure numeric predictions.",
            "Remove duplicate embedded scale when it matches the independent pred_scale.",
            "Preserve textual span and multi-span answers containing non-scale words.",
        ],
        "changed_predictions": changed_predictions,
        "change_tag_counts": dict(change_tag_counts),
        "metrics": modes,
        "events": {
            "raw": event_counts(records, details_by_mode["raw"]),
            "canonicalized": event_counts(records, details_by_mode["canonicalized"]),
        },
        "flip_counts": dict(flip_counter),
        "flips": flips,
        "decision": "FREEZE EVALUATION CONTRACT" if not any(f["direction"] == "worsened" for f in flips) else "FIX EVALUATION FIRST",
    }
    dump_json(AUDIT_JSON_PATH, audit)
    write_report(audit)
    print(json.dumps({
        "sample_n": audit["sample_n"],
        "changed_predictions": changed_predictions,
        "flip_counts": audit["flip_counts"],
        "raw_em": {arm: modes["raw"][arm]["exact_match"] for arm in ARMS},
        "canonicalized_em": {arm: modes["canonicalized"][arm]["exact_match"] for arm in ARMS},
        "decision": audit["decision"],
    }, indent=2))
    return audit


def fmt(v: float) -> str:
    return f"{v:.3f}"


def write_report(audit: dict[str, Any]) -> None:
    lines = [
        "# TAT-QA Output Normalization Audit",
        "",
        "Date: 2026-08-16",
        "",
        "Scope: evaluation-only audit over frozen TAT-QA four-arm dry-run raw outputs. No LLM/API calls, no prompt/retrieval/memory changes.",
        "",
        "## Canonicalization Contract",
        "",
    ]
    for item in audit["normalization_contract"]:
        lines.append(f"- {item}")
    lines.extend([
        "",
        f"Changed predictions: {audit['changed_predictions']} / {audit['sample_n'] * len(audit['arms'])}.",
        f"Change tags: `{audit['change_tag_counts']}`.",
        "",
        "## Raw vs Canonicalized Metrics",
        "",
        "| Arm | Raw EM | Canon EM | Delta EM | Raw F1 | Canon F1 | Delta F1 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for arm in ARMS:
        raw = audit["metrics"]["raw"][arm]
        can = audit["metrics"]["canonicalized"][arm]
        lines.append(
            f"| `{arm}` | {fmt(raw['exact_match'])} | {fmt(can['exact_match'])} | {can['exact_match'] - raw['exact_match']:+.3f} | "
            f"{fmt(raw['f1'])} | {fmt(can['f1'])} | {can['f1'] - raw['f1']:+.3f} |"
        )
    lines.extend([
        "",
        "## Correctness Flips",
        "",
        f"- Flip counts: `{audit['flip_counts']}`.",
    ])
    for f in audit["flips"][:12]:
        lines.append(
            f"- `{f['sample_id']}` arm=`{f['arm']}` {f['direction']} "
            f"raw=({f['raw_em']:.0f},{f['raw_f1']:.2f}) canon=({f['canonicalized_em']:.0f},{f['canonicalized_f1']:.2f}) "
            f"tags={f['change_tags']} pred={f['raw_prediction']} -> {f['canonicalized_prediction']} gold={f['gold_answer']} scale={f['gold_scale'] or 'none'}"
        )
    lines.extend([
        "",
        "## Memory Effect Events",
        "",
        "| Event | Raw | Canonicalized |",
        "|---|---:|---:|",
    ])
    for key in audit["events"]["raw"]:
        lines.append(f"| `{key}` | {audit['events']['raw'][key]} | {audit['events']['canonicalized'][key]} |")
    lines.extend([
        "",
        "## Interpretation",
        "",
        "- Canonicalization is intentionally conservative: it changes only pure numeric/currency answers with optional scale tokens.",
        "- Textual span and multi-span predictions containing ordinary words are preserved.",
        "- The audit measures whether dry-run memory effects were artifacts of answer/scale formatting before any new experiment is run.",
        "",
        "## Decision",
        "",
        f"Decision: `{audit['decision']}`.",
    ])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    run()
