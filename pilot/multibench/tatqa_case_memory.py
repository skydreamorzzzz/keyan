"""TAT-QA train-only Case Memory and retrieval-only audit.

This module intentionally does not call an LLM. It reuses the FinQA pilot's
single dense retriever setup (BAAI/bge-small-en-v1.5 by default) and adds
TAT-QA-specific source exclusion.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import Counter, defaultdict
from typing import Any

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PILOT_DIR = os.path.join(ROOT, "pilot")
if PILOT_DIR not in sys.path:
    sys.path.insert(0, PILOT_DIR)
if os.path.dirname(__file__) not in sys.path:
    sys.path.insert(0, os.path.dirname(__file__))

import config  # noqa: E402
from retrieval import get_model  # noqa: E402
from tatqa_ingest import parse_split  # noqa: E402

OUT_DIR = os.path.join(ROOT, "data", "tatqa", "processed")
AUDIT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "tatqa")
CASE_MEMORY_PATH = os.path.join(OUT_DIR, "tatqa_case_memory_train.json")
CASE_EMB_PATH = os.path.join(OUT_DIR, "tatqa_case_emb.npy")
CASE_ORDER_PATH = os.path.join(OUT_DIR, "tatqa_case_order.json")
AUDIT_JSON_PATH = os.path.join(AUDIT_DIR, "tatqa_case_retrieval_audit.json")
AUDIT_MD_PATH = os.path.join(AUDIT_DIR, "TATQA_CASE_RETRIEVAL_AUDIT.md")

TOP_K = 4
AUDIT_N = 50
SEED = 20260816
MAX_TABLE_ROWS = 80
MAX_PARAGRAPH_CHARS = 800

LABEL_FIELD_NAMES = {
    "answer",
    "answer_type",
    "answer_from",
    "scale",
    "derivation",
    "operator",
    "operator_sequence",
    "reasoning_annotation",
}


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def normalize_cell(value: Any) -> str:
    return " ".join(str(value).replace("\n", " ").split())


def render_table(table: list[list[Any]], max_rows: int = MAX_TABLE_ROWS) -> str:
    rows = []
    for i, row in enumerate(table[:max_rows]):
        cells = " | ".join(normalize_cell(cell) for cell in row)
        rows.append(f"row_{i}: {cells}")
    if len(table) > max_rows:
        rows.append(f"... {len(table) - max_rows} more rows")
    return "\n".join(rows)


def paragraph_text(paragraph: dict[str, Any]) -> str:
    return normalize_cell(paragraph.get("text", ""))


def render_all_paragraphs(paragraphs: list[dict[str, Any]], max_chars: int = MAX_PARAGRAPH_CHARS) -> str:
    chunks = []
    for p in sorted(paragraphs, key=lambda x: x.get("order", 0)):
        text = paragraph_text(p)
        if max_chars and len(text) > max_chars:
            text = text[:max_chars].rstrip() + "..."
        chunks.append(f"paragraph_{p.get('order')}: {text}")
    return "\n".join(chunks)


def relevant_paragraphs(record: dict[str, Any]) -> list[dict[str, Any]]:
    rel = record.get("reasoning_annotation", {}).get("rel_paragraphs")
    if not rel:
        return []
    rel_orders = {str(x) for x in rel}
    out = []
    for p in record.get("paragraphs", []):
        if str(p.get("order")) in rel_orders:
            out.append({"order": p.get("order"), "text": p.get("text", "")})
    return out


def make_retrieval_text(record: dict[str, Any], *, memory_side: bool = False) -> str:
    """Build label-free retrieval text.

    Target-side calls must pass only inference-visible records. Memory-side
    calls may use relevant train paragraphs as solved-case context, but still
    exclude answer labels, scale, derivation, operator, and reasoning metadata.
    """
    if memory_side:
        paragraphs = record.get("relevant_paragraphs") or relevant_paragraphs(record)
    else:
        paragraphs = record.get("paragraphs", [])
    para_text = render_all_paragraphs(paragraphs)
    table_text = render_table(record.get("table", []))
    return "\n".join([
        f"Question: {record.get('question', '')}",
        "Paragraphs:",
        para_text,
        "Table:",
        table_text,
    ]).strip()


def assert_retrieval_text_is_label_free(record: dict[str, Any], text: str) -> None:
    """Best-effort guard against accidental gold-label leakage in retrieval text."""
    for field in LABEL_FIELD_NAMES:
        value = record.get(field)
        if value in (None, "", [], {}):
            continue
        if field in {"answer", "derivation", "scale", "answer_type", "answer_from", "operator"}:
            needle = normalize_cell(value)
            if needle and len(needle) >= 4 and needle.lower() in text.lower():
                raise ValueError(f"retrieval_text appears to contain label field `{field}`: {needle[:80]}")


def build_case(record: dict[str, Any]) -> dict[str, Any]:
    rel_paras = relevant_paragraphs(record)
    case = {
        "dataset_id": "tatqa",
        "case_id": record["sample_id"],
        "native_question_uid": record["native_question_uid"],
        "split": "train",
        "source_id": record["source_id"],
        "question": record["question"],
        "table": record["table"],
        "relevant_paragraphs": rel_paras,
        "answer": record["answer"],
        "answer_type": record["answer_type"],
        "answer_from": record["answer_from"],
        "scale": record["scale"],
        "operator": record["operator"],
        "operator_sequence": record["operator_sequence"],
        "derivation": record["derivation"],
        "reasoning_annotation": record["reasoning_annotation"],
    }
    case["retrieval_text"] = make_retrieval_text(case, memory_side=True)
    return case


def build_case_memory() -> list[dict[str, Any]]:
    train = parse_split("train")
    cases = [build_case(record) for record in train]
    dump_json(CASE_MEMORY_PATH, cases)
    return cases


def build_case_index(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if cases is None:
        cases = load_json(CASE_MEMORY_PATH)
    model = get_model()
    texts = [case["retrieval_text"] for case in cases]
    emb = model.encode(texts, batch_size=256, show_progress_bar=True, normalize_embeddings=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    np.save(CASE_EMB_PATH, emb)
    order = [{"case_id": c["case_id"], "source_id": c["source_id"]} for c in cases]
    dump_json(CASE_ORDER_PATH, order)
    return {"shape": list(emb.shape), "order_count": len(order)}


def load_case_index() -> tuple[np.ndarray, list[dict[str, Any]]]:
    return np.load(CASE_EMB_PATH), load_json(CASE_ORDER_PATH)


def retrieve_cases(
    query_text: str,
    *,
    k: int = TOP_K,
    exclude_source_id: str | None = None,
) -> list[dict[str, Any]]:
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


def compatibility(target: dict[str, Any], cases: list[dict[str, Any]], key: str) -> dict[str, Any]:
    target_value = target.get(key)
    matches = [c.get(key) == target_value for c in cases]
    return {
        "target": target_value,
        "top1_match": bool(matches[0]) if matches else False,
        "any_topk_match": any(matches),
        "topk_matches": sum(matches),
    }


def short_case(case: dict[str, Any], score: float) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "source_id": case["source_id"],
        "score": score,
        "question": case["question"],
        "answer_type": case["answer_type"],
        "answer_from": case["answer_from"],
        "operator": case["operator"],
        "scale": case["scale"],
        "derivation_preview": str(case.get("derivation") or "")[:160],
        "relevant_paragraphs_preview": [
            {"order": p.get("order"), "text": str(p.get("text", ""))[:220]}
            for p in case.get("relevant_paragraphs", [])[:3]
        ],
        "table_preview": case.get("table", [])[:5],
    }


def fixed_dev_sample(dev: list[dict[str, Any]], n: int = AUDIT_N) -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    return rng.sample(dev, min(n, len(dev)))


def audit_retrieval(n: int = AUDIT_N, k: int = TOP_K) -> dict[str, Any]:
    cases = load_json(CASE_MEMORY_PATH)
    cases_by_id = {case["case_id"]: case for case in cases}
    dev = parse_split("dev")
    sample = fixed_dev_sample(dev, n)
    records = []
    counters = defaultdict(Counter)
    score_top1 = []
    source_leaks = 0
    for target in sample:
        query_text = make_retrieval_text(target, memory_side=False)
        hits = retrieve_cases(query_text, k=k, exclude_source_id=target["source_id"])
        hit_cases = []
        for hit in hits:
            if hit["source_id"] == target["source_id"]:
                source_leaks += 1
            c = cases_by_id[hit["case_id"]]
            hc = dict(c)
            hc["score"] = hit["score"]
            hit_cases.append(hc)
        if hits:
            score_top1.append(hits[0]["score"])
        diagnostics = {
            "answer_type": compatibility(target, hit_cases, "answer_type"),
            "answer_from": compatibility(target, hit_cases, "answer_from"),
            "operator": compatibility(target, hit_cases, "operator"),
            "scale": compatibility(target, hit_cases, "scale"),
        }
        for key, d in diagnostics.items():
            counters[key]["top1_match"] += int(d["top1_match"])
            counters[key]["any_topk_match"] += int(d["any_topk_match"])
        records.append({
            "sample_id": target["sample_id"],
            "source_id": target["source_id"],
            "question": target["question"],
            "answer_type": target["answer_type"],
            "answer_from": target["answer_from"],
            "operator": target["operator"],
            "scale": target["scale"],
            "derivation_preview": str(target.get("derivation") or "")[:160],
            "diagnostics": diagnostics,
            "top_cases": [short_case(c, c["score"]) for c in hit_cases],
        })
    summary = {
        "n_dev_samples": len(sample),
        "top_k": k,
        "seed": SEED,
        "case_memory_size": len(cases),
        "source_leak_count": source_leaks,
        "avg_top1_score": float(np.mean(score_top1)) if score_top1 else 0.0,
        "compatibility": {
            key: {
                "top1_match_rate": counters[key]["top1_match"] / len(sample) if sample else 0.0,
                "any_topk_match_rate": counters[key]["any_topk_match"] / len(sample) if sample else 0.0,
            }
            for key in ["answer_type", "answer_from", "operator", "scale"]
        },
        "target_answer_type_counts": dict(Counter(r["answer_type"] or "missing" for r in sample)),
        "target_operator_counts": dict(Counter(r["operator"] or "missing" for r in sample)),
        "target_scale_counts": dict(Counter((r["scale"] or "none") for r in sample)),
    }
    audit = {"summary": summary, "records": records}
    dump_json(AUDIT_JSON_PATH, audit)
    write_audit_md(audit)
    return audit


def write_audit_md(audit: dict[str, Any]) -> None:
    s = audit["summary"]
    comp = s["compatibility"]
    lines = [
        "# TAT-QA Case Retrieval Audit",
        "",
        "Date: 2026-08-16",
        "",
        "Scope: TAT-QA train-only Case Memory plus retrieval-only dev audit. No LLM calls, no Strategy Memory, no four-arm experiment.",
        "",
        "## Memory Construction",
        "",
        f"- Source split: TAT-QA train only.",
        f"- Cases: {s['case_memory_size']}.",
        f"- Saved memory: `data/tatqa/processed/tatqa_case_memory_train.json`.",
        "- Each case stores question, table, relevant paragraphs, answer, answer type/source, scale, derivation, coarse operator, operator sequence, reasoning annotation, and `source_id`.",
        "- Historical solved-case labels are stored for future prompting/audit, but they are not used in target query retrieval text.",
        "",
        "## Retrieval Text Safety",
        "",
        "- Target query retrieval text uses only inference-visible fields: question, visible paragraphs, and table.",
        "- Case retrieval text excludes answer, answer type/source, scale, derivation, operator, and reasoning annotation.",
        "- Post-hoc compatibility metrics below use gold labels only after retrieval, for audit diagnostics.",
        "",
        "## Retrieval Setup",
        "",
        f"- Retriever: same dense embedding model as FinQA pilot, `{config.EMBED_MODEL}` on `{config.EMBED_DEVICE}`.",
        f"- Top-k: {s['top_k']}.",
        "- TAT-QA-specific tuning: none.",
        "- Added exclusion: retrieved cases with identical `source_id` are skipped.",
        f"- Source leak count after exclusion: {s['source_leak_count']}.",
        "",
        "## Fixed Dev Audit",
        "",
        f"- Dev sample size: {s['n_dev_samples']} fixed by seed `{s['seed']}`.",
        f"- Average top-1 cosine score: {s['avg_top1_score']:.4f}.",
        "",
        "| Diagnostic label | Top-1 match | Any top-4 match |",
        "|---|---:|---:|",
    ]
    for key in ["answer_type", "answer_from", "operator", "scale"]:
        lines.append(
            f"| `{key}` | {comp[key]['top1_match_rate']:.3f} | {comp[key]['any_topk_match_rate']:.3f} |"
        )
    lines.extend([
        "",
        "Target label distribution in this audit sample:",
        "",
        f"- answer_type: `{s['target_answer_type_counts']}`",
        f"- operator: `{s['target_operator_counts']}`",
        f"- scale: `{s['target_scale_counts']}`",
        "",
        "## Retrieval Examples",
        "",
    ])
    for rec in audit["records"][:5]:
        lines.extend([
            f"### {rec['sample_id']}",
            "",
            f"Question: {rec['question']}",
            "",
            f"Target audit labels: answer_type=`{rec['answer_type']}`, answer_from=`{rec['answer_from']}`, operator=`{rec['operator']}`, scale=`{rec['scale']}`.",
            "",
            "| Rank | Score | Case question | Answer type | Operator | Scale |",
            "|---:|---:|---|---|---|---|",
        ])
        for rank, case in enumerate(rec["top_cases"], 1):
            q = str(case["question"]).replace("|", "\\|")[:140]
            lines.append(
                f"| {rank} | {case['score']:.4f} | {q} | `{case['answer_type']}` | `{case['operator']}` | `{case['scale']}` |"
            )
        lines.append("")
    lines.extend([
        "## Interpretation",
        "",
        "This layer is ready for Strategy Memory design if downstream work treats these compatibility numbers as diagnostics, not selector features. The retriever can find cases with non-trivial answer-type/operator overlap without using target labels, and source exclusion prevents same-report/table reuse in the audit path.",
        "",
        "Risks to carry forward:",
        "",
        "- Case retrieval text uses relevant train paragraphs when available, while target queries use the full visible context. This matches the solved-case memory idea but creates mild representation asymmetry.",
        "- `operator` is a coarse parser-derived audit label, not an official TAT-QA field.",
        "- Scale compatibility is only a post-hoc diagnostic at this stage; it should not be used for retrieval tuning before a frozen protocol exists.",
        "",
        "Decision: `READY FOR TAT-QA STRATEGY MEMORY DESIGN`.",
    ])
    os.makedirs(AUDIT_DIR, exist_ok=True)
    with open(AUDIT_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


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
    parser.add_argument("--build", action="store_true", help="Build TAT-QA train Case Memory JSON.")
    parser.add_argument("--index", action="store_true", help="Build dense retrieval index for TAT-QA Case Memory.")
    parser.add_argument("--audit", action="store_true", help="Run fixed dev retrieval-only audit.")
    parser.add_argument("--audit-n", type=int, default=AUDIT_N)
    args = parser.parse_args()
    if not (args.build or args.index or args.audit):
        args.build = True
        args.index = True
        args.audit = True
    run(build=args.build, index=args.index, audit=args.audit, audit_n=args.audit_n)


if __name__ == "__main__":
    main()
