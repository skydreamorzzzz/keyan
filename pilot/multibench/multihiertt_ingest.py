"""MultiHiertt ingestion into the project unified intermediate format.

This is a data ingestion and audit script only. It does not build memory,
retrieve examples, run LLMs, or evaluate model outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from typing import Any

import pyarrow.parquet as pq

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW_DIR = os.path.join(ROOT, "data", "multihiertt", "raw")
OUT_DIR = os.path.join(ROOT, "data", "multihiertt", "processed")
AUDIT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "multihiertt")
SOURCE_PATH = os.path.join(ROOT, "data", "multihiertt", "SOURCE.md")
AUDIT_JSON_PATH = os.path.join(AUDIT_DIR, "multihiertt_data_audit.json")
AUDIT_MD_PATH = os.path.join(AUDIT_DIR, "MULTIHIERTT_DATA_AUDIT.md")
SAMPLE20_PATH = os.path.join(OUT_DIR, "multihiertt_unified_sample20.json")

SEED = 20260817
SPLITS = ["train", "validation"]
EXPECTED_ROWS = {"train": 7830, "validation": 1044}
PARQUET_URLS = {
    "train": "https://huggingface.co/api/datasets/bevaya/MultiHiertt/parquet/default/train/0.parquet",
    "validation": "https://huggingface.co/api/datasets/bevaya/MultiHiertt/parquet/default/validation/0.parquet",
}


def load_parquet_rows(split: str) -> list[dict[str, Any]]:
    path = os.path.join(RAW_DIR, f"{split}.parquet")
    table = pq.read_table(path)
    return table.to_pylist()


def md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_json_loads(text: Any) -> tuple[dict[str, Any], bool]:
    if isinstance(text, dict):
        return text, True
    if not text:
        return {}, False
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}, isinstance(obj, dict)
    except Exception:  # noqa: BLE001
        return {}, False


def render_text_context(paragraphs: list[str]) -> str:
    return "\n".join(f"paragraph_{i}: {p}" for i, p in enumerate(paragraphs or []))


def parse_program(program: str) -> dict[str, Any]:
    program = (program or "").strip()
    if not program:
        return {
            "answer_type": "span",
            "operator_sequence": [],
            "operands": [],
            "n_steps": 0,
            "parse_ok": True,
            "parse_error": None,
        }
    ops = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", program)
    operands: list[list[str]] = []
    malformed = False
    for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(([^()]*)\)", program):
        args = [a.strip() for a in match.group(2).split(",") if a.strip()]
        operands.append(args)
    if program.count("(") != program.count(")"):
        malformed = True
    if not ops:
        malformed = True
    if operands and len(operands) != len(ops):
        malformed = True
    return {
        "answer_type": "program",
        "operator_sequence": ops,
        "operands": operands,
        "n_steps": len(ops),
        "parse_ok": not malformed,
        "parse_error": "malformed_program" if malformed else None,
    }


def evidence_text(paragraphs: list[str], indices: list[int]) -> list[dict[str, Any]]:
    out = []
    for idx in indices or []:
        valid = isinstance(idx, int) and 0 <= idx < len(paragraphs)
        out.append({
            "paragraph_index": idx,
            "valid": valid,
            "text": paragraphs[idx] if valid else None,
        })
    return out


def evidence_table_descriptions(table_description: dict[str, str], refs: list[str]) -> list[dict[str, Any]]:
    out = []
    for ref in refs or []:
        out.append({
            "cell_ref": ref,
            "valid": ref in table_description,
            "description": table_description.get(ref),
        })
    return out


def html_table_preview(html: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", html or "").strip()
    return text[:limit]


def parse_row(split: str, row: dict[str, Any], index: int) -> dict[str, Any]:
    uid = row.get("uid") or f"{split}:{index}"
    paragraphs = list(row.get("paragraphs") or [])
    tables = list(row.get("tables") or [])
    table_description, table_description_parse_ok = safe_json_loads(row.get("table_description"))
    text_ev = list(row.get("text_evidence") or [])
    table_ev = list(row.get("table_evidence") or [])
    program = row.get("program") or ""
    parsed_program = parse_program(program)
    return {
        "dataset_id": "multihiertt",
        "sample_id": f"multihiertt:{split}:{uid}",
        "native_uid": uid,
        "split": split,
        "source_id": uid,
        "question": row.get("question") or "",
        "answer": row.get("answer"),
        "paragraphs": paragraphs,
        "text_context": render_text_context(paragraphs),
        "tables": [
            {
                "table_id": str(i),
                "format": "html",
                "html": html,
            }
            for i, html in enumerate(tables)
        ],
        "table_description": table_description,
        "reasoning": {
            "answer_type": parsed_program["answer_type"],
            "program": program,
            "program_dsl": "multihiertt" if program else "none",
            "operator_sequence": parsed_program["operator_sequence"],
            "operands": parsed_program["operands"],
            "n_steps": parsed_program["n_steps"],
            "program_parse_ok": parsed_program["parse_ok"],
            "program_parse_error": parsed_program["parse_error"],
            "evidence": {
                "text": evidence_text(paragraphs, text_ev),
                "table": evidence_table_descriptions(table_description, table_ev),
                "paragraph_indices": text_ev,
                "cell_refs": table_ev,
            },
        },
        "raw_metadata": {
            "row_index": index,
            "table_description_parse_ok": table_description_parse_ok,
            "table_description_cell_count": len(table_description),
            "table_count": len(tables),
            "paragraph_count": len(paragraphs),
            "context_char_len": sum(len(p or "") for p in paragraphs) + sum(len(t or "") for t in tables),
        },
    }


def write_jsonl(path: str, records: list[dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def percentile(values: list[int], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    return float(statistics.quantiles(values, n=100, method="inclusive")[int(pct) - 1])


def dist(values: list[int]) -> dict[str, float]:
    return {
        "min": float(min(values)) if values else 0.0,
        "mean": float(statistics.mean(values)) if values else 0.0,
        "p50": percentile(values, 50),
        "p90": percentile(values, 90),
        "p95": percentile(values, 95),
        "max": float(max(values)) if values else 0.0,
    }


def summarize_split(split: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    answer_type = Counter(r["reasoning"]["answer_type"] for r in records)
    operators = Counter(op for r in records for op in r["reasoning"]["operator_sequence"])
    program_records = [r for r in records if r["reasoning"]["answer_type"] == "program"]
    span_records = [r for r in records if r["reasoning"]["answer_type"] == "span"]
    text_evidence_nonempty = sum(bool(r["reasoning"]["evidence"]["paragraph_indices"]) for r in records)
    table_evidence_nonempty = sum(bool(r["reasoning"]["evidence"]["cell_refs"]) for r in records)
    any_evidence_nonempty = sum(
        bool(r["reasoning"]["evidence"]["paragraph_indices"] or r["reasoning"]["evidence"]["cell_refs"])
        for r in records
    )
    valid_text_refs = sum(
        all(e["valid"] for e in r["reasoning"]["evidence"]["text"])
        for r in records if r["reasoning"]["evidence"]["paragraph_indices"]
    )
    valid_table_refs = sum(
        all(e["valid"] for e in r["reasoning"]["evidence"]["table"])
        for r in records if r["reasoning"]["evidence"]["cell_refs"]
    )
    missing = {
        "uid": sum(not r["native_uid"] for r in records),
        "question": sum(not r["question"] for r in records),
        "answer": sum(r["answer"] in (None, "") for r in records),
        "paragraphs": sum(not r["paragraphs"] for r in records),
        "tables": sum(not r["tables"] for r in records),
        "table_description": sum(not r["table_description"] for r in records),
        "malformed_table_description": sum(not r["raw_metadata"]["table_description_parse_ok"] for r in records),
        "malformed_program": sum(
            r["reasoning"]["answer_type"] == "program" and not r["reasoning"]["program_parse_ok"]
            for r in records
        ),
    }
    return {
        "rows": len(records),
        "expected_rows": EXPECTED_ROWS.get(split),
        "matches_expected_rows": len(records) == EXPECTED_ROWS.get(split),
        "answer_type_counts": dict(answer_type),
        "program_vs_span": {
            "program": len(program_records),
            "span": len(span_records),
            "program_rate": len(program_records) / len(records) if records else 0.0,
        },
        "program_parse_coverage": {
            "program_records": len(program_records),
            "parse_ok": sum(r["reasoning"]["program_parse_ok"] for r in program_records),
            "parse_ok_rate": (
                sum(r["reasoning"]["program_parse_ok"] for r in program_records) / len(program_records)
                if program_records else 0.0
            ),
            "operator_counts": dict(operators),
            "n_steps_distribution": dist([r["reasoning"]["n_steps"] for r in program_records]),
        },
        "evidence_coverage": {
            "text_evidence_nonempty": text_evidence_nonempty,
            "table_evidence_nonempty": table_evidence_nonempty,
            "any_evidence_nonempty": any_evidence_nonempty,
            "text_evidence_nonempty_rate": text_evidence_nonempty / len(records) if records else 0.0,
            "table_evidence_nonempty_rate": table_evidence_nonempty / len(records) if records else 0.0,
            "any_evidence_nonempty_rate": any_evidence_nonempty / len(records) if records else 0.0,
            "text_evidence_all_refs_valid": valid_text_refs,
            "table_evidence_all_refs_valid": valid_table_refs,
        },
        "context_distributions": {
            "table_count": dist([r["raw_metadata"]["table_count"] for r in records]),
            "paragraph_count": dist([r["raw_metadata"]["paragraph_count"] for r in records]),
            "table_description_cell_count": dist([r["raw_metadata"]["table_description_cell_count"] for r in records]),
            "context_char_len": dist([r["raw_metadata"]["context_char_len"] for r in records]),
        },
        "missing_or_malformed": missing,
    }


def short_record(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": rec["sample_id"],
        "split": rec["split"],
        "question": rec["question"],
        "answer": rec["answer"],
        "answer_type": rec["reasoning"]["answer_type"],
        "program": rec["reasoning"]["program"],
        "operator_sequence": rec["reasoning"]["operator_sequence"],
        "text_evidence": rec["reasoning"]["evidence"]["paragraph_indices"],
        "table_evidence": rec["reasoning"]["evidence"]["cell_refs"],
        "paragraph_preview": rec["paragraphs"][:3],
        "table_count": len(rec["tables"]),
        "table_preview": [html_table_preview(t["html"]) for t in rec["tables"][:2]],
        "table_description_preview": dict(list(rec["table_description"].items())[:5]),
    }


def write_source(audit: dict[str, Any]) -> None:
    lines = [
        "# MultiHiertt Source",
        "",
        "Dataset: MultiHiertt, ACL 2022, numerical reasoning over multiple hierarchical financial tables and text.",
        "",
        "Primary/official repository:",
        "- https://github.com/psunlpgroup/MultiHiertt",
        "",
        "Official paper:",
        "- https://aclanthology.org/2022.acl-long.454/",
        "",
        "Downloaded annotation files used in this repo:",
        "- Hugging Face parquet repackaging: https://huggingface.co/datasets/bevaya/MultiHiertt",
        "- Reason: the official GitHub points to JSON data via Google Drive, while this Hugging Face mirror packages only the annotation data in documented parquet form without model checkpoints.",
        "",
        "Files:",
    ]
    for split in SPLITS:
        f = audit["files"][split]
        lines.append(f"- `{f['path']}` from {f['url']} rows={f['rows']} bytes={f['bytes']} md5={f['md5']}")
    lines.extend([
        "",
        "License/provenance notes:",
        "- QA annotations and official code are MIT licensed in the official GitHub repository.",
        "- Underlying table data originates from FinTabNet / public SEC filings; see the Hugging Face dataset card for CDLA-Permissive-1.0 notes.",
        "",
        "Large raw parquet files are intentionally ignored by git because the train parquet is larger than normal GitHub file-size limits. Re-run `pilot/multibench/multihiertt_ingest.py` after downloading them to regenerate processed JSONL and audit artifacts.",
    ])
    os.makedirs(os.path.dirname(SOURCE_PATH), exist_ok=True)
    with open(SOURCE_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_report(audit: dict[str, Any], sample20: list[dict[str, Any]]) -> None:
    lines = [
        "# MultiHiertt Data Audit",
        "",
        "Date: 2026-08-17",
        "",
        "Scope: ingestion and data audit only. No LLM/API calls, no memory construction, no retrieval, no four-arm experiment, no router.",
        "",
        "## Source",
        "",
        "Primary source is the official MultiHiertt GitHub repository (`psunlpgroup/MultiHiertt`) and ACL 2022 paper. The raw files used here are the documented Hugging Face parquet repackaging `bevaya/MultiHiertt`, which contains train/validation annotation data without checkpoints.",
        "See `data/multihiertt/SOURCE.md` for URLs, checksums, and license notes.",
        "",
        "## Split Summary",
        "",
        "| Split | Rows | Expected | Program | Span | Program parse OK | Any evidence | Missing/malformed fields |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for split in SPLITS:
        s = audit["splits"][split]
        miss = {k: v for k, v in s["missing_or_malformed"].items() if v}
        lines.append(
            f"| `{split}` | {s['rows']} | {s['expected_rows']} | {s['program_vs_span']['program']} | "
            f"{s['program_vs_span']['span']} | {s['program_parse_coverage']['parse_ok_rate']:.3f} | "
            f"{s['evidence_coverage']['any_evidence_nonempty_rate']:.3f} | `{miss}` |"
        )
    lines.extend([
        "",
        "## Program / Operator Distribution",
        "",
    ])
    for split in SPLITS:
        p = audit["splits"][split]["program_parse_coverage"]
        lines.append(f"### {split}")
        lines.append(f"- n_steps distribution: `{p['n_steps_distribution']}`")
        lines.append(f"- top operators: `{dict(Counter(p['operator_counts']).most_common(12))}`")
        lines.append("")
    lines.extend([
        "## Evidence Coverage",
        "",
        "| Split | Text evidence non-empty | Table evidence non-empty | Any evidence non-empty | Text refs valid | Table refs valid |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for split in SPLITS:
        e = audit["splits"][split]["evidence_coverage"]
        lines.append(
            f"| `{split}` | {e['text_evidence_nonempty_rate']:.3f} | {e['table_evidence_nonempty_rate']:.3f} | "
            f"{e['any_evidence_nonempty_rate']:.3f} | {e['text_evidence_all_refs_valid']} | {e['table_evidence_all_refs_valid']} |"
        )
    lines.extend([
        "",
        "## Context Length Distributions",
        "",
    ])
    for split in SPLITS:
        lines.append(f"### {split}")
        for key, value in audit["splits"][split]["context_distributions"].items():
            lines.append(f"- `{key}`: `{value}`")
        lines.append("")
    lines.extend([
        "## Unified IR Mapping",
        "",
        "- `question` / `answer`: copied from parquet columns.",
        "- `paragraphs`: list of document sentences, preserving `## Table N ##` placeholders.",
        "- `tables`: list of raw hierarchical HTML tables, one object per table.",
        "- `table_description`: JSON-decoded cell description mapping; not forced into a flat table matrix.",
        "- `reasoning.program`: original MultiHiertt flat DSL string, retained as-is.",
        "- `reasoning.operator_sequence`: deterministic parse of operator names for audit only.",
        "- `reasoning.evidence.text` / `reasoning.evidence.table`: gold evidence ids plus resolved text/cell descriptions where available.",
        "",
        "## Sample20",
        "",
        f"Deterministic sanity sample saved to `{os.path.relpath(SAMPLE20_PATH, ROOT)}` with seed `{SEED}`.",
        "",
        "## Decision",
        "",
        f"Decision: `{audit['decision']}`.",
    ])
    os.makedirs(AUDIT_DIR, exist_ok=True)
    with open(AUDIT_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run() -> dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(AUDIT_DIR, exist_ok=True)
    records_by_split = {}
    files = {}
    for split in SPLITS:
        path = os.path.join(RAW_DIR, f"{split}.parquet")
        rows = load_parquet_rows(split)
        records = [parse_row(split, row, i) for i, row in enumerate(rows)]
        records_by_split[split] = records
        write_jsonl(os.path.join(OUT_DIR, f"multihiertt_{split}.jsonl"), records)
        files[split] = {
            "path": os.path.relpath(path, ROOT),
            "url": PARQUET_URLS[split],
            "rows": len(rows),
            "bytes": os.path.getsize(path),
            "md5": md5(path),
        }
    audit = {
        "dataset_id": "multihiertt",
        "version": "multihiertt_ingest_v1",
        "source": {
            "official_github": "https://github.com/psunlpgroup/MultiHiertt",
            "official_paper": "https://aclanthology.org/2022.acl-long.454/",
            "downloaded_from": "https://huggingface.co/datasets/bevaya/MultiHiertt",
        },
        "files": files,
        "splits": {split: summarize_split(split, records) for split, records in records_by_split.items()},
    }
    problems = []
    for split, summary in audit["splits"].items():
        if not summary["matches_expected_rows"]:
            problems.append(f"{split}: row count mismatch")
        if summary["missing_or_malformed"]["malformed_table_description"]:
            problems.append(f"{split}: malformed table_description")
        if summary["missing_or_malformed"]["malformed_program"]:
            problems.append(f"{split}: malformed program")
    audit["decision"] = "READY FOR EVALUATOR" if not problems else "FIX INGESTION FIRST"
    audit["blocking_problems"] = problems
    rng = random.Random(SEED)
    all_records = records_by_split["train"] + records_by_split["validation"]
    sample20 = [short_record(r) for r in rng.sample(all_records, 20)]
    write_json(SAMPLE20_PATH, sample20)
    write_json(AUDIT_JSON_PATH, audit)
    write_source(audit)
    write_report(audit, sample20)
    print(json.dumps({
        "splits": {
            split: {
                "rows": audit["splits"][split]["rows"],
                "program": audit["splits"][split]["program_vs_span"]["program"],
                "span": audit["splits"][split]["program_vs_span"]["span"],
                "parse_ok_rate": audit["splits"][split]["program_parse_coverage"]["parse_ok_rate"],
            }
            for split in SPLITS
        },
        "decision": audit["decision"],
        "report": os.path.relpath(AUDIT_MD_PATH, ROOT),
    }, indent=2))
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
