"""Offline MultiHiertt Strategy structure audit.

This script analyzes deterministic structure over MultiHiertt train samples.
It does not generate Strategy Memory, retrieve, run LLM/API calls, execute
prompts, or build a router.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from typing import Any

import pyarrow.parquet as pq

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW_DIR = os.path.join(ROOT, "data", "multihiertt", "raw")
OUT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "multihiertt")
AUDIT_JSON_PATH = os.path.join(OUT_DIR, "multihiertt_strategy_structure_audit.json")
AUDIT_MD_PATH = os.path.join(OUT_DIR, "MULTIHIERTT_STRATEGY_STRUCTURE_AUDIT.md")

OP_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(([^()]*)\)")
NUMBER_RE = re.compile(r"\$?-?\d+(?:,\d{3})*(?:\.\d+)?%?|const_[A-Za-z0-9_]+|#\d+")
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
COMPARISON_RE = re.compile(
    r"\b(greater|less|larger|smaller|higher|lower|most|least|maximum|max|min|minimum|greatest|largest|lowest|"
    r"more|fewer|exceed|exceeds|exceeded|increase|decrease|decline|growth)\b",
    re.I,
)
YESNO_RE = re.compile(r"^(does|do|did|is|are|was|were|has|have|had)\b", re.I)
SUPERLATIVE_RE = re.compile(r"\b(most|least|maximum|max|min|minimum|greatest|largest|lowest|highest)\b", re.I)
RATIO_RE = re.compile(r"\b(ratio|proportion|percent|percentage|rate|multiple)\b", re.I)
AGG_RE = re.compile(r"\b(sum|total|average|avg|mean)\b", re.I)


def load_rows(split: str = "train") -> list[dict[str, Any]]:
    return pq.read_table(os.path.join(RAW_DIR, f"{split}.parquet")).to_pylist()


def dump_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def pct(count: int, total: int) -> float:
    return count / total if total else 0.0


def answer_type(row: dict[str, Any]) -> str:
    return "program" if (row.get("program") or "").strip() else "span"


def parse_steps(program: str) -> list[dict[str, Any]]:
    steps = []
    for match in OP_RE.finditer(program or ""):
        args = [arg.strip() for arg in match.group(2).split(",") if arg.strip()]
        steps.append({"op": match.group(1), "args": args})
    return steps


def operator_sequence(program: str) -> list[str]:
    return [step["op"] for step in parse_steps(program)]


def operator_family_from_ops(ops: list[str]) -> str:
    if not ops:
        return "none"
    return "+".join(sorted(set(ops)))


def operand_count(program: str) -> int:
    operands = []
    for step in parse_steps(program):
        operands.extend(arg for arg in step["args"] if not arg.startswith("#"))
    return len(operands)


def unique_table_ids(refs: list[str]) -> set[str]:
    ids = set()
    for ref in refs or []:
        text = str(ref)
        if "-" in text:
            ids.add(text.split("-", 1)[0])
    return ids


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


def table_usage(row: dict[str, Any]) -> dict[str, Any]:
    table_ids = unique_table_ids(row.get("table_evidence") or [])
    html = "\n".join(row.get("tables") or [])
    hierarchy_markers = {
        "rowspan": len(re.findall(r"\browspan\s*=", html, flags=re.I)),
        "colspan": len(re.findall(r"\bcolspan\s*=", html, flags=re.I)),
        "th": len(re.findall(r"<\s*th\b", html, flags=re.I)),
    }
    return {
        "table_count": len(row.get("tables") or []),
        "evidence_table_count": len(table_ids),
        "multi_table_evidence": len(table_ids) > 1,
        "has_table_evidence": bool(table_ids),
        "hierarchy_marker_count": sum(hierarchy_markers.values()),
        "has_hierarchy_markers": any(v > 0 for v in hierarchy_markers.values()),
        "hierarchy_markers": hierarchy_markers,
    }


def scale_hint(question: str) -> str:
    q = question.lower()
    if "%" in q or "percent" in q or "percentage" in q:
        return "percent"
    if "billion" in q or "billions" in q or "(in b" in q:
        return "billion"
    if "million" in q or "millions" in q:
        return "million"
    if "thousand" in q or "thousands" in q:
        return "thousand"
    return "none"


def normalized_program_template(program: str) -> str:
    rendered = []
    for step in parse_steps(program):
        args = []
        for arg in step["args"]:
            if arg.startswith("#"):
                args.append("<result>")
            elif arg.startswith("const_"):
                args.append("<const>")
            else:
                args.append("<operand>")
        rendered.append(f"{step['op']}({', '.join(args)})")
    return ", ".join(rendered) if rendered else ""


def program_family(row: dict[str, Any]) -> str:
    ops = operator_sequence(row.get("program") or "")
    if not ops:
        return "program:unparsed"
    counts = Counter(ops)
    seq = ">".join(ops)
    q = row.get("question") or ""
    if ops == ["divide"] and RATIO_RE.search(q):
        return "program:ratio"
    if ops == ["subtract", "divide"] or (counts["subtract"] and counts["divide"] and "multiply" not in counts):
        if RATIO_RE.search(q) or "growth" in q.lower() or "rate" in q.lower():
            return "program:change_rate"
        return "program:difference_then_ratio"
    if ops == ["add"] or (set(ops) == {"add"} and len(ops) >= 1):
        return "program:aggregation_sum"
    if counts["add"] and counts["divide"] and not counts["subtract"]:
        return "program:average_or_composed_division"
    if ops == ["subtract"]:
        return "program:difference"
    if ops == ["multiply"]:
        return "program:multiplication"
    if counts["multiply"] and counts["divide"] and counts["subtract"]:
        return "program:projection_or_compound_change"
    if counts["divide"]:
        return "program:division_composition"
    if counts["subtract"]:
        return "program:difference_composition"
    if counts["multiply"]:
        return "program:multiplication_composition"
    return f"program:sequence:{seq}"


def span_family(row: dict[str, Any]) -> str:
    q = row.get("question") or ""
    q_lower = q.lower()
    answer = str(row.get("answer") or "")
    if YESNO_RE.search(q) and COMPARISON_RE.search(q):
        return "span:comparison_yesno"
    if SUPERLATIVE_RE.search(q):
        return "span:superlative_lookup"
    if COMPARISON_RE.search(q):
        return "span:comparison_lookup"
    if "," in answer or ";" in answer:
        return "span:multi_value_lookup"
    if AGG_RE.search(q_lower) or RATIO_RE.search(q_lower):
        return "span:computed_value_lookup"
    return "span:direct_lookup"


def abstract_record(row: dict[str, Any], index: int) -> dict[str, Any]:
    atype = answer_type(row)
    ops = operator_sequence(row.get("program") or "")
    usage = table_usage(row)
    family = program_family(row) if atype == "program" else span_family(row)
    schema_key = "|".join([
        atype,
        family,
        f"ops={operator_family_from_ops(ops) if ops else 'none'}",
        f"steps={len(ops)}" if atype == "program" and len(ops) <= 4 else "steps=5plus" if atype == "program" else "steps=0",
        f"ev={evidence_modality(row)}",
        f"tables={'multi' if usage['multi_table_evidence'] else 'single' if usage['has_table_evidence'] else 'none'}",
        f"scale={scale_hint(row.get('question') or '')}",
    ])
    return {
        "sample_id": f"multihiertt:train:{row.get('uid') or index}",
        "native_uid": row.get("uid"),
        "answer_type": atype,
        "family": family,
        "schema_key": schema_key,
        "operator_sequence": ops,
        "operator_family": operator_family_from_ops(ops) if ops else "none",
        "step_count": len(ops),
        "operand_count": operand_count(row.get("program") or ""),
        "evidence_modality": evidence_modality(row),
        "table_usage": usage,
        "scale_hint": scale_hint(row.get("question") or ""),
        "normalized_program_template": normalized_program_template(row.get("program") or "") if atype == "program" else "",
        "question_template": question_template(row.get("question") or "") if atype == "span" else "",
    }


def question_template(question: str) -> str:
    q = question.lower()
    q = YEAR_RE.sub("<year>", q)
    q = NUMBER_RE.sub("<num>", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q


def cumulative(counter: Counter, ks: list[int]) -> dict[str, float]:
    total = sum(counter.values())
    counts = [count for _, count in counter.most_common()]
    out = {}
    for k in ks:
        out[f"top_{k}"] = pct(sum(counts[:k]), total)
    return out


def bucket_step_count(n: int) -> str:
    if n == 0:
        return "0"
    if n <= 4:
        return str(n)
    return "5plus"


def build_audit() -> dict[str, Any]:
    rows = load_rows("train")
    abstractions = [abstract_record(row, i) for i, row in enumerate(rows)]
    answer_counts = Counter(a["answer_type"] for a in abstractions)
    family_counts = Counter(a["family"] for a in abstractions)
    schema_counts = Counter(a["schema_key"] for a in abstractions)
    op_seq_counts = Counter(">".join(a["operator_sequence"]) or "none" for a in abstractions)
    op_family_counts = Counter(a["operator_family"] for a in abstractions)
    ev_counts = Counter(a["evidence_modality"] for a in abstractions)
    table_bucket_counts = Counter(
        "multi_table" if a["table_usage"]["multi_table_evidence"]
        else "single_table" if a["table_usage"]["has_table_evidence"]
        else "no_table_evidence"
        for a in abstractions
    )
    hierarchy_counts = Counter("has_hierarchy" if a["table_usage"]["has_hierarchy_markers"] else "no_hierarchy" for a in abstractions)
    step_counts = Counter(bucket_step_count(a["step_count"]) for a in abstractions)
    operand_counts = Counter(str(a["operand_count"]) if a["operand_count"] <= 8 else "9plus" for a in abstractions)
    joint_counts = Counter(
        (
            a["answer_type"],
            a["family"],
            a["operator_family"],
            bucket_step_count(a["step_count"]),
            a["evidence_modality"],
            "multi_table" if a["table_usage"]["multi_table_evidence"] else "single_table" if a["table_usage"]["has_table_evidence"] else "no_table",
            a["scale_hint"],
        )
        for a in abstractions
    )
    program_abs = [a for a in abstractions if a["answer_type"] == "program"]
    span_abs = [a for a in abstractions if a["answer_type"] == "span"]
    pilot_families = choose_pilot_families(family_counts, schema_counts)
    audit = {
        "dataset_id": "multihiertt",
        "split": "train",
        "count": len(rows),
        "answer_type_counts": dict(answer_counts),
        "program_count": len(program_abs),
        "span_count": len(span_abs),
        "operator_sequence_counts": dict(op_seq_counts.most_common(40)),
        "operator_family_counts": dict(op_family_counts.most_common(40)),
        "step_count_buckets": dict(step_counts),
        "operand_count_buckets": dict(operand_counts),
        "evidence_modality_counts": dict(ev_counts),
        "table_usage_counts": dict(table_bucket_counts),
        "hierarchy_marker_counts": dict(hierarchy_counts),
        "coarse_family_count": len(family_counts),
        "schema_family_count": len(schema_counts),
        "coarse_family_coverage": cumulative(family_counts, [5, 10, 15, 20, 30, 50]),
        "schema_family_coverage": cumulative(schema_counts, [5, 10, 20, 30, 50, 100]),
        "top_coarse_families": dict(family_counts.most_common(30)),
        "top_schema_families": dict(schema_counts.most_common(40)),
        "top_joint_patterns": [
            {
                "answer_type": key[0],
                "family": key[1],
                "operator_family": key[2],
                "step_bucket": key[3],
                "evidence_modality": key[4],
                "table_usage": key[5],
                "scale_hint": key[6],
                "count": count,
                "rate": pct(count, len(rows)),
            }
            for key, count in joint_counts.most_common(30)
        ],
        "program_examples": examples(program_abs, 10),
        "span_examples": examples(span_abs, 10),
        "recommended_strategy_schema": recommended_schema(),
        "small_llm_pilot_family_set": pilot_families,
        "decision": "PROCEED SMALL-LLM STRATEGY PILOT",
    }
    dump_json(AUDIT_JSON_PATH, audit)
    write_report(audit)
    return audit


def examples(records: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    out = []
    seen = set()
    for rec in records:
        if rec["family"] in seen:
            continue
        seen.add(rec["family"])
        out.append({
            "sample_id": rec["sample_id"],
            "family": rec["family"],
            "schema_key": rec["schema_key"],
            "operator_sequence": rec["operator_sequence"],
            "step_count": rec["step_count"],
            "operand_count": rec["operand_count"],
            "evidence_modality": rec["evidence_modality"],
            "table_usage": {
                "evidence_table_count": rec["table_usage"]["evidence_table_count"],
                "multi_table_evidence": rec["table_usage"]["multi_table_evidence"],
                "has_hierarchy_markers": rec["table_usage"]["has_hierarchy_markers"],
            },
            "scale_hint": rec["scale_hint"],
            "normalized_program_template": rec["normalized_program_template"],
            "question_template": rec["question_template"],
        })
        if len(out) >= n:
            break
    return out


def choose_pilot_families(family_counts: Counter, schema_counts: Counter) -> dict[str, Any]:
    coarse = [family for family, _ in family_counts.most_common(12)]
    schema = [schema for schema, _ in schema_counts.most_common(20)]
    counts = {family: family_counts[family] for family in coarse}
    return {
        "selection_rule": "top 12 coarse families plus top 20 schema keys by train support; fixed before any LLM abstraction",
        "coarse_families": coarse,
        "coarse_family_counts": counts,
        "schema_keys": schema,
        "estimated_coarse_coverage": pct(sum(counts.values()), sum(family_counts.values())),
        "estimated_schema_coverage": pct(sum(schema_counts[s] for s in schema), sum(schema_counts.values())),
        "recommended_examples_per_family": "4-6 representative train examples in next round, with company/year/number/answer redaction",
    }


def recommended_schema() -> dict[str, Any]:
    return {
        "strategy_id": "multihiertt_strategy:<family_hash>",
        "dataset_id": "multihiertt",
        "strategy_type": "program | span_lookup | span_comparison | span_superlative | span_multi_value",
        "family": "coarse deterministic family",
        "schema_key": "answer_type + family + operator_family + step bucket + evidence modality + table usage + scale hint",
        "program_dsl": "multihiertt_original_flat_dsl_for_program_families",
        "operator_sequence": ["add", "divide"],
        "operator_family": "add+divide",
        "step_count_bucket": "0 | 1 | 2 | 3 | 4 | 5plus",
        "operand_count_bucket": "0..8 | 9plus",
        "evidence_modality": "text | table | text+table | none",
        "table_usage": {
            "table_count": "document table count",
            "evidence_table_count": "number of unique table ids in gold table evidence",
            "multi_table_evidence": "bool",
            "hierarchy_marker_count": "rowspan/colspan/th marker count from HTML",
        },
        "scale_hint": "none | percent | thousand | million | billion",
        "normalized_program_template": "program with numeric literals/references replaced by <operand>",
        "span_question_template": "label-free normalized question pattern for span families",
        "source_support_count": 123,
        "source_sample_ids": ["multihiertt:train:..."],
        "retrieval_text": "future semantic abstraction, generated without concrete company/year/number/answer leakage",
    }


def write_report(audit: dict[str, Any]) -> None:
    lines = [
        "# MultiHiertt Strategy Structure Audit",
        "",
        "Date: 2026-08-17",
        "",
        "Scope: deterministic offline structure audit over MultiHiertt train only. No LLM/API calls, no Strategy Memory generation, no retrieval, no four-arm experiment, no router.",
        "",
        "## Train Distribution",
        "",
        f"- Train samples: {audit['count']}.",
        f"- Program/span: program {audit['program_count']} / span {audit['span_count']}.",
        f"- Answer type counts: `{audit['answer_type_counts']}`.",
        f"- Evidence modality: `{audit['evidence_modality_counts']}`.",
        f"- Table evidence usage: `{audit['table_usage_counts']}`.",
        f"- HTML hierarchy markers: `{audit['hierarchy_marker_counts']}`.",
        "",
        "## Program Structure",
        "",
        "- Program samples retain the original MultiHiertt flat DSL. This audit extracts structure for grouping only; it does not convert programs into FinQA DSL.",
        f"- Operator family counts: `{audit['operator_family_counts']}`.",
        f"- Step-count buckets: `{audit['step_count_buckets']}`.",
        f"- Operand-count buckets: `{audit['operand_count_buckets']}`.",
        "",
        "Top operator sequences:",
        "",
        "| Operator sequence | Count | Rate |",
        "|---|---:|---:|",
    ]
    for seq, count in list(audit["operator_sequence_counts"].items())[:20]:
        lines.append(f"| `{seq}` | {count} | {pct(count, audit['count']):.3f} |")
    lines.extend([
        "",
        "## Span Structure",
        "",
        "- Span samples are kept separate from program schema.",
        "- Deterministic span families use question intent only: direct lookup, comparison yes/no, comparison lookup, superlative lookup, multi-value lookup, and computed-value lookup.",
        "- Span family labels are for Strategy design/audit, not official answer_type fields.",
        "",
        "## Family Coverage",
        "",
        f"- Coarse families: {audit['coarse_family_count']}.",
        f"- Fine schema families: {audit['schema_family_count']}.",
        f"- Coarse cumulative coverage: `{audit['coarse_family_coverage']}`.",
        f"- Schema cumulative coverage: `{audit['schema_family_coverage']}`.",
        "",
        "Top coarse families:",
        "",
        "| Family | Count | Rate |",
        "|---|---:|---:|",
    ])
    for family, count in audit["top_coarse_families"].items():
        lines.append(f"| `{family}` | {count} | {pct(count, audit['count']):.3f} |")
    lines.extend([
        "",
        "Top fine schema families:",
        "",
        "| Schema key | Count | Rate |",
        "|---|---:|---:|",
    ])
    for schema, count in list(audit["top_schema_families"].items())[:25]:
        lines.append(f"| `{schema}` | {count} | {pct(count, audit['count']):.3f} |")
    lines.extend([
        "",
        "## Top Joint Patterns",
        "",
        "| Family | Operator family | Steps | Evidence | Tables | Scale | Count | Rate |",
        "|---|---|---:|---|---|---|---:|---:|",
    ])
    for item in audit["top_joint_patterns"][:20]:
        lines.append(
            f"| `{item['family']}` | `{item['operator_family']}` | `{item['step_bucket']}` | "
            f"`{item['evidence_modality']}` | `{item['table_usage']}` | `{item['scale_hint']}` | "
            f"{item['count']} | {item['rate']:.3f} |"
        )
    lines.extend([
        "",
        "## Program Examples",
        "",
        "| Family | Operators | Steps | Operands | Evidence | Tables | Template |",
        "|---|---|---:|---:|---|---|---|",
    ])
    for ex in audit["program_examples"]:
        tmpl = ex["normalized_program_template"].replace("|", "\\|")[:120]
        table = "multi" if ex["table_usage"]["multi_table_evidence"] else "single" if ex["table_usage"]["evidence_table_count"] else "none"
        lines.append(
            f"| `{ex['family']}` | `{'>'.join(ex['operator_sequence'])}` | {ex['step_count']} | "
            f"{ex['operand_count']} | `{ex['evidence_modality']}` | `{table}` | `{tmpl}` |"
        )
    lines.extend([
        "",
        "## Span Examples",
        "",
        "| Family | Evidence | Tables | Scale | Question template |",
        "|---|---|---|---|---|",
    ])
    for ex in audit["span_examples"]:
        table = "multi" if ex["table_usage"]["multi_table_evidence"] else "single" if ex["table_usage"]["evidence_table_count"] else "none"
        tmpl = ex["question_template"].replace("|", "\\|")[:140]
        lines.append(f"| `{ex['family']}` | `{ex['evidence_modality']}` | `{table}` | `{ex['scale_hint']}` | `{tmpl}` |")
    pilot = audit["small_llm_pilot_family_set"]
    lines.extend([
        "",
        "## Recommended Strategy Schema",
        "",
        "```json",
        json.dumps(audit["recommended_strategy_schema"], indent=2),
        "```",
        "",
        "## Small-LLM Pilot Family Set",
        "",
        f"- Selection rule: {pilot['selection_rule']}.",
        f"- Estimated coarse coverage: {pilot['estimated_coarse_coverage']:.3f}.",
        f"- Estimated schema coverage: {pilot['estimated_schema_coverage']:.3f}.",
        f"- Recommended examples per family: {pilot['recommended_examples_per_family']}.",
        "",
        "Coarse families to cover first:",
        "",
    ])
    for family in pilot["coarse_families"]:
        lines.append(f"- `{family}`: {pilot['coarse_family_counts'][family]}")
    lines.extend([
        "",
        "## Recommendation",
        "",
        "- Program strategies should be generated from deterministic schema plus original MultiHiertt DSL structure; do not ask an LLM to invent formulas.",
        "- Span strategies should be semantic evidence-location strategies, with comparison/superlative/direct lookup kept separate from arithmetic.",
        "- Multi-table and hierarchy usage should be explicit strategy metadata because MultiHiertt often requires linking evidence across several HTML tables.",
        "- The next LLM pilot should only abstract high-support families into reusable reasoning/evidence-location descriptions with company names, years, numbers, and answers redacted.",
        "",
        "## Decision",
        "",
        f"Decision: `{audit['decision']}`.",
    ])
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(AUDIT_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    audit = build_audit()
    print(json.dumps({
        "count": audit["count"],
        "program": audit["program_count"],
        "span": audit["span_count"],
        "coarse_families": audit["coarse_family_count"],
        "schema_families": audit["schema_family_count"],
        "decision": audit["decision"],
        "report": os.path.relpath(AUDIT_MD_PATH, ROOT),
    }, indent=2))


if __name__ == "__main__":
    main()
