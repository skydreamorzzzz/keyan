"""MultiHiertt train-only Case Memory and retrieval-only audit.

This module does not call an LLM. It reuses the project dense retriever model
(`BAAI/bge-small-en-v1.5` by default) and audits retrieval alignment on a fixed
validation sample with gold labels used only post hoc.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from typing import Any

import numpy as np
import pyarrow.parquet as pq

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PILOT_DIR = os.path.join(ROOT, "pilot")
if PILOT_DIR not in sys.path:
    sys.path.insert(0, PILOT_DIR)

import config  # noqa: E402
from retrieval import get_model  # noqa: E402

RAW_DIR = os.path.join(ROOT, "data", "multihiertt", "raw")
OUT_DIR = os.path.join(ROOT, "data", "multihiertt", "processed")
AUDIT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "multihiertt")
CASE_MEMORY_PATH = os.path.join(OUT_DIR, "multihiertt_case_memory_train.json")
CASE_EMB_PATH = os.path.join(OUT_DIR, "multihiertt_case_emb.npy")
CASE_ORDER_PATH = os.path.join(OUT_DIR, "multihiertt_case_order.json")
AUDIT_JSON_PATH = os.path.join(AUDIT_DIR, "multihiertt_case_retrieval_audit.json")
AUDIT_MD_PATH = os.path.join(AUDIT_DIR, "MULTIHIERTT_CASE_RETRIEVAL_AUDIT.md")

TOP_K = 4
AUDIT_N = 120
SEED = 20260817
MAX_PARAGRAPH_CHARS = 220
MAX_EVIDENCE_CHARS = 320
MAX_TABLE_DESC = 80
MAX_RETRIEVAL_TABLES = 4


def load_parquet_rows(split: str) -> list[dict[str, Any]]:
    return pq.read_table(os.path.join(RAW_DIR, f"{split}.parquet")).to_pylist()


def dump_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def safe_table_description(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(k): normalize_text(v) for k, v in value.items()}
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): normalize_text(v) for k, v in parsed.items()}


def source_hash(row: dict[str, Any]) -> str:
    payload = json.dumps(
        {"paragraphs": row.get("paragraphs") or [], "tables": row.get("tables") or []},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def answer_type(row: dict[str, Any]) -> str:
    return "program" if (row.get("program") or "").strip() else "span"


def parse_operator_sequence(program: str) -> list[str]:
    if not program:
        return []
    return re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", program)


def operator_family(row: dict[str, Any]) -> str:
    ops = parse_operator_sequence(row.get("program") or "")
    if not ops:
        return "span_lookup"
    return "+".join(sorted(set(ops)))


def evidence_modality(row: dict[str, Any]) -> str:
    has_text = bool(row.get("text_evidence"))
    has_table = bool(row.get("table_evidence"))
    if has_text and has_table:
        return "text+table"
    if has_text:
        return "text"
    if has_table:
        return "table"
    return "none"


def resolve_text_evidence(row: dict[str, Any]) -> list[dict[str, Any]]:
    paragraphs = row.get("paragraphs") or []
    out = []
    for idx in row.get("text_evidence") or []:
        valid = isinstance(idx, int) and 0 <= idx < len(paragraphs)
        out.append({
            "paragraph_index": idx,
            "valid": valid,
            "text": paragraphs[idx] if valid else None,
        })
    return out


def resolve_table_evidence(row: dict[str, Any]) -> list[dict[str, Any]]:
    desc = safe_table_description(row.get("table_description"))
    out = []
    for ref in row.get("table_evidence") or []:
        out.append({
            "cell_ref": ref,
            "valid": ref in desc,
            "description": desc.get(ref),
        })
    return out


def render_html_preview(html: str, limit: int = 500) -> str:
    return normalize_text(html)[:limit]


def render_all_visible_context(row: dict[str, Any]) -> str:
    paragraphs = []
    for i, text in enumerate(row.get("paragraphs") or []):
        t = normalize_text(text)
        if len(t) > MAX_PARAGRAPH_CHARS:
            t = t[:MAX_PARAGRAPH_CHARS].rstrip() + "..."
        paragraphs.append(f"paragraph_{i}: {t}")
    table_bits = []
    for i, html in enumerate((row.get("tables") or [])[:MAX_RETRIEVAL_TABLES]):
        table_bits.append(f"table_{i}: {render_html_preview(html, 700)}")
    desc = safe_table_description(row.get("table_description"))
    desc_bits = [f"{k}: {v}" for k, v in list(desc.items())[:MAX_TABLE_DESC]]
    return "\n".join([
        "Paragraphs:",
        "\n".join(paragraphs),
        "Hierarchical HTML tables:",
        "\n".join(table_bits),
        "Table cell descriptions:",
        "\n".join(desc_bits),
    ]).strip()


def render_gold_evidence_context(case: dict[str, Any]) -> str:
    text_bits = []
    for item in case.get("text_evidence_resolved", []):
        t = normalize_text(item.get("text"))
        if len(t) > MAX_EVIDENCE_CHARS:
            t = t[:MAX_EVIDENCE_CHARS].rstrip() + "..."
        text_bits.append(f"paragraph_{item.get('paragraph_index')}: {t}")
    table_bits = []
    for item in case.get("table_evidence_resolved", [])[:MAX_TABLE_DESC]:
        table_bits.append(f"{item.get('cell_ref')}: {normalize_text(item.get('description'))}")
    if not text_bits and not table_bits:
        return render_all_visible_context(case)
    return "\n".join([
        "Gold evidence text:",
        "\n".join(text_bits),
        "Gold evidence table cells:",
        "\n".join(table_bits),
    ]).strip()


def make_target_retrieval_text(row: dict[str, Any]) -> str:
    return "\n".join([
        f"Question: {row.get('question', '')}",
        render_all_visible_context(row),
    ]).strip()


def make_case_retrieval_text(case: dict[str, Any]) -> str:
    return "\n".join([
        f"Question: {case.get('question', '')}",
        render_gold_evidence_context(case),
    ]).strip()


def build_case(row: dict[str, Any], split: str, index: int) -> dict[str, Any]:
    desc = safe_table_description(row.get("table_description"))
    case = {
        "dataset_id": "multihiertt",
        "case_id": f"multihiertt:{split}:{row.get('uid') or index}",
        "native_uid": row.get("uid"),
        "split": split,
        "source_id": source_hash(row),
        "question": row.get("question") or "",
        "answer": row.get("answer"),
        "answer_type": answer_type(row),
        "program": row.get("program") or "",
        "operator_sequence": parse_operator_sequence(row.get("program") or ""),
        "operator_family": operator_family(row),
        "evidence_modality": evidence_modality(row),
        "paragraphs": row.get("paragraphs") or [],
        "tables": [
            {"table_id": str(i), "format": "html", "html": html}
            for i, html in enumerate(row.get("tables") or [])
        ],
        "table_description": desc,
        "text_evidence": row.get("text_evidence") or [],
        "table_evidence": row.get("table_evidence") or [],
        "text_evidence_resolved": resolve_text_evidence(row),
        "table_evidence_resolved": resolve_table_evidence(row),
    }
    case["retrieval_text"] = make_case_retrieval_text(case)
    return case


def build_case_memory() -> list[dict[str, Any]]:
    train = load_parquet_rows("train")
    cases = [build_case(row, "train", i) for i, row in enumerate(train)]
    dump_json(CASE_MEMORY_PATH, cases)
    return cases


def build_case_index(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if cases is None:
        cases = load_json(CASE_MEMORY_PATH)
    model = get_model()
    texts = [case["retrieval_text"] for case in cases]
    emb = model.encode(texts, batch_size=128, show_progress_bar=True, normalize_embeddings=True)
    np.save(CASE_EMB_PATH, emb)
    order = [{"case_id": c["case_id"], "source_id": c["source_id"]} for c in cases]
    dump_json(CASE_ORDER_PATH, order)
    return {"shape": list(emb.shape), "order_count": len(order)}


def load_case_index() -> tuple[np.ndarray, list[dict[str, Any]]]:
    return np.load(CASE_EMB_PATH), load_json(CASE_ORDER_PATH)


def retrieve_cases(query_text: str, *, k: int = TOP_K, exclude_source_id: str | None = None) -> list[dict[str, Any]]:
    emb, order = load_case_index()
    model = get_model()
    q = model.encode([query_text], normalize_embeddings=True)[0]
    sims = emb @ q
    ranked = np.argsort(-sims)
    out = []
    for i in ranked:
        meta = order[int(i)]
        if exclude_source_id and meta.get("source_id") == exclude_source_id:
            continue
        out.append({
            "case_id": meta["case_id"],
            "source_id": meta.get("source_id"),
            "score": float(sims[int(i)]),
        })
        if len(out) >= k:
            break
    return out


def fixed_validation_sample(rows: list[dict[str, Any]], n: int = AUDIT_N) -> list[tuple[int, dict[str, Any]]]:
    rng = random.Random(SEED)
    indexed = list(enumerate(rows))
    return rng.sample(indexed, min(n, len(indexed)))


def compatibility(target: dict[str, Any], cases: list[dict[str, Any]], key: str) -> dict[str, Any]:
    target_value = target.get(key)
    matches = [case.get(key) == target_value for case in cases]
    return {
        "target": target_value,
        "top1_match": bool(matches[0]) if matches else False,
        "any_topk_match": any(matches),
        "topk_matches": int(sum(matches)),
    }


def short_case(case: dict[str, Any], score: float) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "source_id": case["source_id"],
        "score": score,
        "question": case["question"],
        "answer_type": case["answer_type"],
        "operator_family": case["operator_family"],
        "operator_sequence": case["operator_sequence"],
        "evidence_modality": case["evidence_modality"],
        "answer_preview": str(case.get("answer"))[:80],
        "program_preview": str(case.get("program") or "")[:160],
        "text_evidence_preview": [
            {"paragraph_index": e.get("paragraph_index"), "text": normalize_text(e.get("text"))[:180]}
            for e in case.get("text_evidence_resolved", [])[:2]
        ],
        "table_evidence_preview": [
            {"cell_ref": e.get("cell_ref"), "description": normalize_text(e.get("description"))[:180]}
            for e in case.get("table_evidence_resolved", [])[:4]
        ],
        "table_count": len(case.get("tables", [])),
    }


def duplicate_document_audit(train: list[dict[str, Any]], validation: list[dict[str, Any]]) -> dict[str, Any]:
    train_hashes = Counter(source_hash(row) for row in train)
    val_hashes = Counter(source_hash(row) for row in validation)
    overlap = sorted(set(train_hashes) & set(val_hashes))
    return {
        "source_id_definition": "md5(json({paragraphs, tables}, sort_keys=True))",
        "train_unique_sources": len(train_hashes),
        "validation_unique_sources": len(val_hashes),
        "overlap_source_count": len(overlap),
        "overlap_validation_questions": int(sum(val_hashes[h] for h in overlap)),
        "overlap_train_cases": int(sum(train_hashes[h] for h in overlap)),
        "largest_train_questions_per_source": train_hashes.most_common(10),
        "overlap_source_ids": overlap[:20],
    }


def summarize_case_memory(cases: list[dict[str, Any]], train_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "case_count": len(cases),
        "program_cases": sum(c["answer_type"] == "program" for c in cases),
        "span_cases": sum(c["answer_type"] == "span" for c in cases),
        "operator_family_counts": dict(Counter(c["operator_family"] for c in cases).most_common(20)),
        "evidence_modality_counts": dict(Counter(c["evidence_modality"] for c in cases)),
        "unique_sources": len({c["source_id"] for c in cases}),
        "source_count_note": "MultiHiertt parquet lacks explicit report id; source_id uses stable document hash.",
        "raw_rows": len(train_rows),
    }


def audit_retrieval(n: int = AUDIT_N, k: int = TOP_K) -> dict[str, Any]:
    cases = load_json(CASE_MEMORY_PATH)
    cases_by_id = {case["case_id"]: case for case in cases}
    train_rows = load_parquet_rows("train")
    val_rows = load_parquet_rows("validation")
    sample = fixed_validation_sample(val_rows, n)
    records = []
    counters = defaultdict(Counter)
    score_top1 = []
    all_scores = []
    source_leaks = 0
    excluded_overlap_targets = 0
    for index, row in sample:
        target = build_case(row, "validation", index)
        query_text = make_target_retrieval_text(row)
        hits = retrieve_cases(query_text, k=k, exclude_source_id=target["source_id"])
        if any(source_hash(row) == h for h in {c["source_id"] for c in cases}):
            excluded_overlap_targets += 1
        hit_cases = []
        for hit in hits:
            if hit["source_id"] == target["source_id"]:
                source_leaks += 1
            case = dict(cases_by_id[hit["case_id"]])
            case["score"] = hit["score"]
            hit_cases.append(case)
            all_scores.append(hit["score"])
        if hits:
            score_top1.append(hits[0]["score"])
        diagnostics = {
            "answer_type": compatibility(target, hit_cases, "answer_type"),
            "operator_family": compatibility(target, hit_cases, "operator_family"),
            "evidence_modality": compatibility(target, hit_cases, "evidence_modality"),
        }
        for key, d in diagnostics.items():
            counters[key]["top1_match"] += int(d["top1_match"])
            counters[key]["any_topk_match"] += int(d["any_topk_match"])
        records.append({
            "sample_id": target["case_id"],
            "native_uid": target["native_uid"],
            "source_id": target["source_id"],
            "question": target["question"],
            "answer_type": target["answer_type"],
            "operator_family": target["operator_family"],
            "operator_sequence": target["operator_sequence"],
            "evidence_modality": target["evidence_modality"],
            "diagnostics": diagnostics,
            "top_cases": [short_case(case, case["score"]) for case in hit_cases],
        })
    strong_successes = [
        r for r in records
        if r["diagnostics"]["answer_type"]["top1_match"]
        and r["diagnostics"]["operator_family"]["top1_match"]
        and r["diagnostics"]["evidence_modality"]["top1_match"]
    ][:5]
    failures = [
        r for r in records
        if not r["diagnostics"]["answer_type"]["any_topk_match"]
        or not r["diagnostics"]["operator_family"]["any_topk_match"]
    ][:5]
    summary = {
        "validation_sample_size": len(sample),
        "seed": SEED,
        "top_k": k,
        "retriever": {"model": config.EMBED_MODEL, "device": config.EMBED_DEVICE},
        "case_memory": summarize_case_memory(cases, train_rows),
        "duplicate_document_audit": duplicate_document_audit(train_rows, val_rows),
        "source_leak_count_after_exclusion": source_leaks,
        "sample_targets_with_train_source_overlap": excluded_overlap_targets,
        "avg_top1_score": float(np.mean(score_top1)) if score_top1 else 0.0,
        "avg_retrieved_score": float(np.mean(all_scores)) if all_scores else 0.0,
        "min_top1_score": float(np.min(score_top1)) if score_top1 else 0.0,
        "max_top1_score": float(np.max(score_top1)) if score_top1 else 0.0,
        "compatibility": {
            key: {
                "top1_match_rate": counters[key]["top1_match"] / len(sample) if sample else 0.0,
                "any_topk_match_rate": counters[key]["any_topk_match"] / len(sample) if sample else 0.0,
            }
            for key in ["answer_type", "operator_family", "evidence_modality"]
        },
        "target_answer_type_counts": dict(Counter(r["answer_type"] for r in records)),
        "target_operator_family_counts": dict(Counter(r["operator_family"] for r in records).most_common(20)),
        "target_evidence_modality_counts": dict(Counter(r["evidence_modality"] for r in records)),
        "example_successes": strong_successes,
        "example_failures": failures,
    }
    audit = {"summary": summary, "records": records}
    dump_json(AUDIT_JSON_PATH, audit)
    write_report(audit)
    return audit


def write_report(audit: dict[str, Any]) -> None:
    s = audit["summary"]
    comp = s["compatibility"]
    dup = s["duplicate_document_audit"]
    mem = s["case_memory"]
    lines = [
        "# MultiHiertt Case Retrieval Audit",
        "",
        "Date: 2026-08-17",
        "",
        "Scope: train-only Case Memory plus retrieval-only validation audit. No LLM/API calls, no Strategy Memory, no four-arm experiment, no router.",
        "",
        "## Case Memory",
        "",
        "- Source split: MultiHiertt train only.",
        f"- Cases: {mem['case_count']} = program {mem['program_cases']} + span {mem['span_cases']}.",
        "- Each case stores question, answer, original program or span answer, gold text/table evidence, table hierarchy as raw HTML, table descriptions, operator sequence/family, and source_id.",
        f"- Unique source ids: {mem['unique_sources']}.",
        "- Full case memory is local-only because raw HTML tables make it too large for normal GitHub commits: `data/multihiertt/processed/multihiertt_case_memory_train.json`.",
        "",
        "## Retrieval Safety",
        "",
        "- Target retrieval text uses only inference-visible fields: question, visible paragraphs, visible hierarchical HTML table previews, and visible table cell descriptions.",
        "- Target retrieval text does not use gold answer, program, text evidence, table evidence, answer type, or operator family.",
        "- Case retrieval text uses solved-case question plus historical gold evidence context. It does not use the case answer/program as retrieval text.",
        "- Post-hoc compatibility metrics below use gold fields only after retrieval for diagnostics.",
        "",
        "## Retrieval Setup",
        "",
        f"- Retriever: `{s['retriever']['model']}` on `{s['retriever']['device']}`.",
        f"- Top-k: {s['top_k']}.",
        "- Tuning: none.",
        "- Source exclusion: same source_id skipped during retrieval.",
        f"- Source leak count after exclusion: {s['source_leak_count_after_exclusion']}.",
        "",
        "## Source / Duplicate Document Audit",
        "",
        f"- Source id definition: `{dup['source_id_definition']}`.",
        f"- Train unique sources: {dup['train_unique_sources']}.",
        f"- Validation unique sources: {dup['validation_unique_sources']}.",
        f"- Train-validation overlapping sources: {dup['overlap_source_count']} source(s), covering {dup['overlap_validation_questions']} validation question(s) and {dup['overlap_train_cases']} train case(s).",
        f"- Fixed audit sample targets with train source overlap: {s['sample_targets_with_train_source_overlap']}.",
        "- The dataset lacks explicit report/document ids in the parquet release, so document-hash source exclusion is the current leakage guard.",
        "",
        "## Fixed Validation Audit",
        "",
        f"- Validation sample size: {s['validation_sample_size']} fixed by seed `{s['seed']}`.",
        f"- Average top-1 score: {s['avg_top1_score']:.4f}.",
        f"- Average retrieved score across top-{s['top_k']}: {s['avg_retrieved_score']:.4f}.",
        f"- Top-1 score range: {s['min_top1_score']:.4f} to {s['max_top1_score']:.4f}.",
        "",
        "| Diagnostic label | Top-1 match | Any top-4 match |",
        "|---|---:|---:|",
    ]
    for key in ["answer_type", "operator_family", "evidence_modality"]:
        lines.append(f"| `{key}` | {comp[key]['top1_match_rate']:.3f} | {comp[key]['any_topk_match_rate']:.3f} |")
    lines.extend([
        "",
        "Target distribution in fixed validation sample:",
        "",
        f"- answer_type: `{s['target_answer_type_counts']}`",
        f"- operator_family: `{s['target_operator_family_counts']}`",
        f"- evidence_modality: `{s['target_evidence_modality_counts']}`",
        "",
        "## Typical Successful Retrievals",
        "",
    ])
    for rec in s["example_successes"][:3]:
        lines.extend(render_example(rec))
    lines.extend(["## Typical Failure Modes", ""])
    for rec in s["example_failures"][:3]:
        lines.extend(render_example(rec))
    lines.extend([
        "## Interpretation",
        "",
        "The retrieval layer is usable as a frozen diagnostic baseline if downstream work treats compatibility as post-hoc audit only. The most important caveat is source provenance: the parquet release lacks explicit report ids, so source exclusion relies on deterministic document hashes over paragraphs and HTML tables.",
        "",
        "Decision: `READY FOR STRATEGY DESIGN`.",
    ])
    os.makedirs(AUDIT_DIR, exist_ok=True)
    with open(AUDIT_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def render_example(rec: dict[str, Any]) -> list[str]:
    lines = [
        f"### {rec['sample_id']}",
        "",
        f"Question: {rec['question']}",
        "",
        f"Target labels: answer_type=`{rec['answer_type']}`, operator_family=`{rec['operator_family']}`, evidence_modality=`{rec['evidence_modality']}`.",
        "",
        "| Rank | Score | Case question | Answer type | Operator family | Evidence modality |",
        "|---:|---:|---|---|---|---|",
    ]
    for rank, case in enumerate(rec["top_cases"], 1):
        question = str(case["question"]).replace("|", "\\|")[:150]
        lines.append(
            f"| {rank} | {case['score']:.4f} | {question} | `{case['answer_type']}` | "
            f"`{case['operator_family']}` | `{case['evidence_modality']}` |"
        )
    lines.append("")
    return lines


def run(build: bool, index: bool, audit: bool, audit_n: int) -> dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(AUDIT_DIR, exist_ok=True)
    result: dict[str, Any] = {}
    cases = None
    if build:
        cases = build_case_memory()
        result["case_memory"] = {"path": os.path.relpath(CASE_MEMORY_PATH, ROOT), "count": len(cases)}
    if index:
        idx = build_case_index(cases)
        result["index"] = {
            "emb_path": os.path.relpath(CASE_EMB_PATH, ROOT),
            "order_path": os.path.relpath(CASE_ORDER_PATH, ROOT),
            **idx,
        }
    if audit:
        audit_result = audit_retrieval(n=audit_n)
        result["audit"] = {
            "json": os.path.relpath(AUDIT_JSON_PATH, ROOT),
            "md": os.path.relpath(AUDIT_MD_PATH, ROOT),
            "summary": audit_result["summary"],
        }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--index", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--audit-n", type=int, default=AUDIT_N)
    args = parser.parse_args()
    if not (args.build or args.index or args.audit):
        args.build = True
        args.index = True
        args.audit = True
    run(build=args.build, index=args.index, audit=args.audit, audit_n=args.audit_n)


if __name__ == "__main__":
    main()
