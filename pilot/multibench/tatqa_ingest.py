"""TAT-QA ingestion into the project unified intermediate format.

This script performs dataset parsing and schema audit only. It does not build
memory, call LLMs, or run task experiments.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import argparse
from collections import Counter, defaultdict
from statistics import mean
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW_DIR = os.path.join(ROOT, "data", "tatqa", "raw")
OUT_DIR = os.path.join(ROOT, "data", "tatqa", "processed")
AUDIT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "tatqa")
SEED = 20260816

EXPECTED_MD5 = {
    "train": "cc5026bdfe51bb47d63e6c3d31714951",
    "dev": "0b24a68b35fd814df5ad12cba548a8ea",
    "test": "c6ccc2beecaed12fc070c3df102ca019",
}


def load_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def raw_path(split: str) -> str:
    return os.path.join(RAW_DIR, f"tatqa_dataset_{split}.json")


def render_text_context(paragraphs: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"paragraph_{p.get('order')}: {p.get('text', '')}"
        for p in sorted(paragraphs, key=lambda p: p.get("order", 0))
    )


def infer_operator(question: dict[str, Any]) -> str | None:
    """Infer a coarse operator label from TAT-QA annotation when available."""
    answer_type = question.get("answer_type")
    if not answer_type:
        return None
    if question.get("req_comparison"):
        return "comparison"
    if answer_type in {"span", "spans", "multi-span", "multi_span"}:
        return "span" if answer_type == "span" else "multi_span"
    if answer_type in {"count", "counting"}:
        return "count"
    derivation = str(question.get("derivation") or "")
    if answer_type == "arithmetic":
        ops = infer_operator_sequence(derivation)
        return ops[-1] if ops else "arithmetic"
    return str(answer_type)


def infer_operator_sequence(derivation: str) -> list[str]:
    """Small heuristic over TAT-QA's human-readable derivation string."""
    if not derivation:
        return []
    ops = []
    if "+" in derivation:
        ops.append("add")
    if "-" in derivation:
        ops.append("subtract")
    if "*" in derivation or "×" in derivation or " x " in derivation.lower():
        ops.append("multiply")
    if "/" in derivation or "÷" in derivation:
        ops.append("divide")
    if re.search(r"\baverage\b|\bavg\b", derivation, re.I):
        ops.append("average")
    if "##" in derivation:
        ops.append("count_or_multi_item")
    return ops


def answer_value(question: dict[str, Any]) -> Any:
    return question.get("answer") if "answer" in question else None


def parse_context(split: str, context: dict[str, Any], context_index: int) -> list[dict[str, Any]]:
    table = context["table"]["table"]
    table_uid = context["table"]["uid"]
    paragraphs = context.get("paragraphs", [])
    text_context = render_text_context(paragraphs)
    rows = []
    for q in context.get("questions", []):
        sample_id = f"tatqa:{split}:{q['uid']}"
        derivation = q.get("derivation")
        operator_sequence = infer_operator_sequence(derivation or "")
        rows.append({
            "dataset_id": "tatqa",
            "sample_id": sample_id,
            "native_question_uid": q["uid"],
            "split": split,
            "source_id": table_uid,
            "context_index": context_index,
            "question_order": q.get("order"),
            "question": q.get("question", ""),
            "text_context": text_context,
            "paragraphs": paragraphs,
            "table": table,
            "table_uid": table_uid,
            "answer": answer_value(q),
            "answer_type": q.get("answer_type"),
            "answer_from": q.get("answer_from"),
            "operator": infer_operator(q),
            "operator_sequence": operator_sequence,
            "scale": q.get("scale"),
            "derivation": derivation,
            "reasoning_annotation": {
                "derivation": derivation,
                "rel_paragraphs": q.get("rel_paragraphs"),
                "req_comparison": q.get("req_comparison"),
                "answer_type": q.get("answer_type"),
                "answer_from": q.get("answer_from"),
            },
            "has_gold_answer": "answer" in q,
            "has_derivation": bool(derivation),
        })
    return rows


def parse_split(split: str) -> list[dict[str, Any]]:
    raw = load_json(raw_path(split))
    records = []
    for i, context in enumerate(raw):
        records.extend(parse_context(split, context, i))
    return records


def write_jsonl(path: str, records: list[dict[str, Any]]) -> None:
    with open(path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def short_record(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": rec["sample_id"],
        "split": rec["split"],
        "source_id": rec["source_id"],
        "question": rec["question"],
        "answer": rec["answer"],
        "answer_type": rec["answer_type"],
        "operator": rec["operator"],
        "scale": rec["scale"],
        "derivation": rec["derivation"],
        "text_context_preview": rec["text_context"][:500],
        "table_preview": rec["table"][:5],
    }


def summarize(records_by_split: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    audit: dict[str, Any] = {"splits": {}, "md5": {}}
    for split, records in records_by_split.items():
        raw = load_json(raw_path(split))
        audit["md5"][split] = {
            "path": os.path.relpath(raw_path(split), ROOT),
            "actual": md5(raw_path(split)),
            "expected": EXPECTED_MD5[split],
            "matches_expected": md5(raw_path(split)) == EXPECTED_MD5[split],
        }
        q_per_context = [len(c.get("questions", [])) for c in raw]
        table_shapes = [
            [len(c["table"]["table"]), max((len(r) for r in c["table"]["table"]), default=0)]
            for c in raw
        ]
        paragraph_counts = [len(c.get("paragraphs", [])) for c in raw]
        answer_types = Counter(r["answer_type"] or "missing" for r in records)
        operators = Counter(r["operator"] or "missing" for r in records)
        scales = Counter((r["scale"] if r["scale"] not in {None, ""} else "none") for r in records)
        answer_from = Counter(r["answer_from"] or "missing" for r in records)
        missing = {
            "answer": sum(1 for r in records if r["answer"] is None),
            "operator": sum(1 for r in records if r["operator"] is None),
            "scale": sum(1 for r in records if r["scale"] is None),
            "derivation": sum(1 for r in records if not r["derivation"]),
            "text_context": sum(1 for r in records if not r["text_context"]),
            "table": sum(1 for r in records if not r["table"]),
        }
        audit["splits"][split] = {
            "contexts": len(raw),
            "questions": len(records),
            "avg_questions_per_context": float(mean(q_per_context)) if q_per_context else 0.0,
            "avg_paragraphs_per_context": float(mean(paragraph_counts)) if paragraph_counts else 0.0,
            "avg_table_rows": float(mean(s[0] for s in table_shapes)) if table_shapes else 0.0,
            "avg_table_cols_maxrow": float(mean(s[1] for s in table_shapes)) if table_shapes else 0.0,
            "top_level_context_keys": sorted(raw[0].keys()) if raw else [],
            "question_keys": sorted(raw[0]["questions"][0].keys()) if raw and raw[0].get("questions") else [],
            "answer_type_counts": dict(answer_types),
            "operator_counts": dict(operators),
            "scale_counts": dict(scales),
            "answer_from_counts": dict(answer_from),
            "missing_counts": missing,
        }
    return audit


def make_sanity_sample(records_by_split: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    train_dev = records_by_split["train"] + records_by_split["dev"]
    rng = random.Random(SEED)
    sample = rng.sample(train_dev, 20)
    return [short_record(r) for r in sample]


def write_audit_md(audit: dict[str, Any], sanity: list[dict[str, Any]]) -> None:
    lines = [
        "# TAT-QA Data Audit",
        "",
        "Date: 2026-08-16",
        "",
        "Scope: data ingestion and schema audit only. No memory construction, no LLM calls, no four-arm experiment.",
        "",
        "## Source",
        "",
        "Raw data was downloaded from the official TAT-QA GitHub raw files linked by https://nextplusplus.github.io/TAT-QA/.",
        "See `data/tatqa/SOURCE.md` for URLs, MD5 checksums, and license notes.",
        "",
        "## Split Summary",
        "",
        "| Split | Contexts | Questions | Gold answers missing | Derivation missing | Answer types |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for split, s in audit["splits"].items():
        lines.append(
            f"| {split} | {s['contexts']} | {s['questions']} | "
            f"{s['missing_counts']['answer']} | {s['missing_counts']['derivation']} | "
            f"`{s['answer_type_counts']}` |"
        )
    lines.extend([
        "",
        "MD5 checks passed for all three downloaded files.",
        "",
        "## Field Mapping",
        "",
        "| Unified field | TAT-QA source | Notes |",
        "|---|---|---|",
        "| `dataset_id` | constant | `tatqa` |",
        "| `sample_id` | `question.uid` | Prefixed as `tatqa:{split}:{uid}` |",
        "| `question` | `questions[].question` | One flattened record per question |",
        "| `text_context` | `paragraphs[].order/text` | Rendered as ordered paragraphs |",
        "| `table` | `table.table` | Matrix of strings |",
        "| `answer` | `questions[].answer` | Missing in public test |",
        "| `operator` | answer type + derivation heuristic | Span/count from answer type; arithmetic uses derivation symbols when possible |",
        "| `scale` | `questions[].scale` | Missing in public test |",
        "| `derivation` | `questions[].derivation` | Empty for span/multi-span and absent in public test |",
        "| `reasoning_annotation` | answer type/source, derivation, rel paragraphs, comparison flag | Raw annotation preserved |",
        "",
        "## Missing / Anomaly Notes",
        "",
        "- Public test has question-only records: no `answer`, `answer_type`, `answer_from`, `scale`, or `derivation`.",
        "- Train/dev span and multi-span questions usually have empty derivation by design.",
        "- `operator` is not a native TAT-QA field. The parser derives a coarse label from `answer_type`, `req_comparison`, and arithmetic symbols in `derivation`.",
        "- `scale` is an empty string for no-scale answers in train/dev; it is `null` for public test records.",
        "- The current parser keeps full paragraphs/table matrix in each flattened record. If storage becomes a concern, records can be normalized by context id later.",
        "",
        "## Sanity Sample",
        "",
        "A deterministic random sample of 20 train/dev records is saved to `data/tatqa/processed/tatqa_unified_sample20.json`.",
        "",
        "| # | Split | Question | Answer | Operator | Scale | Derivation |",
        "|---:|---|---|---|---|---|---|",
    ])
    for i, rec in enumerate(sanity, 1):
        q = str(rec["question"]).replace("|", "\\|")
        ans = json.dumps(rec["answer"], ensure_ascii=False).replace("|", "\\|")
        deriv = str(rec["derivation"] or "").replace("|", "\\|")
        lines.append(
            f"| {i} | {rec['split']} | {q[:120]} | `{ans}` | "
            f"`{rec['operator']}` | `{rec['scale']}` | `{deriv[:80]}` |"
        )
    lines.extend([
        "",
        "## Next Step Toward Memory",
        "",
        "Case Memory should store the flattened query, table, relevant paragraphs, answer type/source, scale, derivation, and raw reasoning annotation.",
        "Strategy Memory should start only from train/dev records with executable or interpretable reasoning annotations: arithmetic derivations, counting derivations, and comparison flags.",
        "Before any LLM experiments, add a TAT-QA evaluator wrapper using the official answer+scale metric.",
    ])
    with open(os.path.join(AUDIT_DIR, "TATQA_DATA_AUDIT.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


def run(write_full: bool = False) -> dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(AUDIT_DIR, exist_ok=True)
    records_by_split = {split: parse_split(split) for split in ["train", "dev", "test"]}
    if write_full:
        for split, records in records_by_split.items():
            write_jsonl(os.path.join(OUT_DIR, f"tatqa_unified_{split}.jsonl"), records)
        all_records = [r for split in ["train", "dev", "test"] for r in records_by_split[split]]
        write_jsonl(os.path.join(OUT_DIR, "tatqa_unified_all.jsonl"), all_records)
    sanity = make_sanity_sample(records_by_split)
    with open(os.path.join(OUT_DIR, "tatqa_unified_sample20.json"), "w") as f:
        json.dump(sanity, f, indent=2, ensure_ascii=False)
    audit = summarize(records_by_split)
    with open(os.path.join(AUDIT_DIR, "tatqa_data_audit.json"), "w") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)
    write_audit_md(audit, sanity)
    print(json.dumps({
        "splits": {k: {"contexts": v["contexts"], "questions": v["questions"], "missing": v["missing_counts"]} for k, v in audit["splits"].items()},
        "full_unified_jsonl_written": write_full,
        "sample20": os.path.relpath(os.path.join(OUT_DIR, "tatqa_unified_sample20.json"), ROOT),
        "audit": os.path.relpath(os.path.join(AUDIT_DIR, "TATQA_DATA_AUDIT.md"), ROOT),
    }, indent=2))
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-full", action="store_true", help="Write full flattened unified JSONL files. They are large because context is repeated per question.")
    args = parser.parse_args()
    run(write_full=args.write_full)
