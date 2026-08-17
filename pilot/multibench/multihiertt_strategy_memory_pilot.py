"""MultiHiertt Strategy Memory v0 small pilot.

Family/schema definitions are frozen from
`multihiertt_strategy_structure_audit.py`. This script builds a small Strategy
Memory pilot only; it does not run retrieval, four-arm execution, or routing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PILOT_DIR = os.path.join(ROOT, "pilot")
if PILOT_DIR not in sys.path:
    sys.path.insert(0, PILOT_DIR)
if os.path.dirname(__file__) not in sys.path:
    sys.path.insert(0, os.path.dirname(__file__))

import llm  # noqa: E402
from multihiertt_strategy_structure_audit import (  # noqa: E402
    AUDIT_JSON_PATH as STRUCTURE_AUDIT_JSON_PATH,
    abstract_record,
    load_rows,
)

OUT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "multihiertt")
DATA_OUT_DIR = os.path.join(ROOT, "data", "multihiertt", "processed")
MEMORY_PATH = os.path.join(DATA_OUT_DIR, "multihiertt_strategy_memory_v0.json")
AUDIT_JSON_PATH = os.path.join(OUT_DIR, "multihiertt_strategy_memory_pilot_audit.json")
REPORT_PATH = os.path.join(OUT_DIR, "MULTIHIERTT_STRATEGY_MEMORY_PILOT.md")
CACHE_PATH = os.path.join(OUT_DIR, "multihiertt_strategy_memory_v0_llm_cache.jsonl")

PILOT_VERSION = "multihiertt_strategy_memory_v0_top12coarse_top20schema_frozen_v1"
TOP_COARSE_N = 12
TOP_SCHEMA_N = 20
EXAMPLES_PER_GROUP = 6
MAX_LLM_CALLS = 32
LLM_MAX_TOKENS = 1400

REQUIRED_STRATEGY_KEYS = {
    "strategy_id",
    "dataset_id",
    "version",
    "strategy_level",
    "strategy_type",
    "family",
    "schema_key",
    "source_support_count",
    "source_sample_ids",
    "operator_sequence",
    "operator_family",
    "normalized_program_template",
    "evidence_modality",
    "table_usage",
    "scale_hint",
    "representative_examples_redacted",
    "description",
    "reasoning_guidance",
    "evidence_guidance",
    "operand_roles",
    "answer_form",
    "scale_notes",
    "multi_table_notes",
    "risk_notes",
    "retrieval_text",
    "generation",
}

SYSTEM = (
    "You write reusable, label-free MultiHiertt financial QA strategy abstractions. "
    "Never solve an example. Never include company names, specific years, specific numbers, "
    "specific answers, copied report phrases, or concrete table values. Return only JSON."
)

LLM_SCHEMA = {
    "description": "one general sentence about when this strategy applies",
    "reasoning_guidance": ["2-4 short bullets about the reasoning pattern"],
    "evidence_guidance": ["2-4 short bullets for locating text/table evidence"],
    "operand_roles": ["2-5 abstract roles such as target metric, base period, component values"],
    "answer_form": "how the final answer should be expressed",
    "scale_notes": ["1-3 notes about unit/scale/percent handling"],
    "multi_table_notes": ["1-3 notes for hierarchical or multi-table evidence"],
    "risk_notes": ["1-3 common failure modes"],
}

LEAK_PATTERNS = {
    "four_digit_year": re.compile(r"\b(?:19|20)\d{2}\b"),
    "currency_or_large_number": re.compile(r"\$\s*\d|\b\d{1,3}(?:,\d{3})+\b|\b\d+\.\d+\b"),
    "standalone_number": re.compile(r"\b\d+\b"),
}


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def load_jsonl_cache(path: str) -> dict[str, dict[str, Any]]:
    cache = {}
    if not os.path.exists(path):
        return cache
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                cache[rec["key"]] = rec
    return cache


def append_jsonl(path: str, rec: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def rewrite_jsonl(path: str, records: list[dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def normalize_space(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def strategy_type(absr: dict[str, Any]) -> str:
    if absr["answer_type"] == "program":
        return "program"
    family = absr["family"]
    if family == "span:comparison_yesno":
        return "span_comparison_yesno"
    if family == "span:comparison_lookup":
        return "span_comparison_lookup"
    if family == "span:superlative_lookup":
        return "span_superlative_lookup"
    if family == "span:multi_value_lookup":
        return "span_multi_value_lookup"
    if family == "span:computed_value_lookup":
        return "span_computed_value_lookup"
    return "span_direct_lookup"


def table_bucket(absr: dict[str, Any]) -> str:
    usage = absr["table_usage"]
    if usage["multi_table_evidence"]:
        return "multi"
    if usage["has_table_evidence"]:
        return "single"
    return "none"


def small_count_label(value: int) -> str:
    labels = {
        0: "zero",
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
    }
    return labels.get(value, "many")


def group_examples(items: list[dict[str, Any]], n: int = EXAMPLES_PER_GROUP) -> list[dict[str, Any]]:
    out = []
    seen = set()
    for item in items:
        absr = item["abstraction"]
        key = (
            tuple(absr["operator_sequence"]),
            absr["evidence_modality"],
            table_bucket(absr),
            absr["scale_hint"],
            absr["normalized_program_template"],
            absr["question_template"],
        )
        if key in seen:
            continue
        seen.add(key)
        ex = {
            "strategy_type": strategy_type(absr),
            "family": absr["family"],
            "operator_sequence": absr["operator_sequence"],
            "operator_family": absr["operator_family"],
            "step_count_bucket": small_count_label(absr["step_count"]),
            "operand_count_bucket": small_count_label(absr["operand_count"]),
            "evidence_modality": absr["evidence_modality"],
            "table_usage": {
                "evidence_table_count_bucket": "multi" if absr["table_usage"]["multi_table_evidence"] else "single" if absr["table_usage"]["has_table_evidence"] else "none",
                "has_hierarchy_markers": bool(absr["table_usage"]["has_hierarchy_markers"]),
            },
            "scale_hint": absr["scale_hint"],
            "normalized_program_template": absr["normalized_program_template"],
            "span_question_intent": absr["family"] if absr["answer_type"] == "span" else "",
        }
        out.append(ex)
        if len(out) >= n:
            break
    return out


def build_groups(rows: list[dict[str, Any]], structure_audit: dict[str, Any]) -> list[dict[str, Any]]:
    abstractions = [{"row": row, "abstraction": abstract_record(row, i)} for i, row in enumerate(rows)]
    by_family = defaultdict(list)
    by_schema = defaultdict(list)
    family_counts = Counter()
    schema_counts = Counter()
    for item in abstractions:
        absr = item["abstraction"]
        by_family[absr["family"]].append(item)
        by_schema[absr["schema_key"]].append(item)
        family_counts[absr["family"]] += 1
        schema_counts[absr["schema_key"]] += 1
    top_coarse = list((structure_audit.get("top_coarse_families") or {}).keys())[:TOP_COARSE_N]
    top_schema = list((structure_audit.get("top_schema_families") or {}).keys())[:TOP_SCHEMA_N]
    groups = []
    for family in top_coarse:
        items = by_family[family]
        first = items[0]["abstraction"]
        groups.append({
            "level": "coarse",
            "group_key": family,
            "family": family,
            "schema_key": "coarse:" + family,
            "support_count": family_counts[family],
            "items": items,
            "prototype": first,
        })
    for schema_key in top_schema:
        items = by_schema[schema_key]
        first = items[0]["abstraction"]
        groups.append({
            "level": "schema",
            "group_key": schema_key,
            "family": first["family"],
            "schema_key": schema_key,
            "support_count": schema_counts[schema_key],
            "items": items,
            "prototype": first,
        })
    if len(groups) > MAX_LLM_CALLS:
        raise RuntimeError(f"Planned group count exceeds budget: {len(groups)} > {MAX_LLM_CALLS}")
    return groups


def prompt_for_group(group: dict[str, Any]) -> str:
    proto = group["prototype"]
    payload = {
        "task": "Create reusable MultiHiertt strategy guidance for this frozen family/schema.",
        "frozen_group": {
            "strategy_level": group["level"],
            "family": group["family"],
            "schema_key": group["schema_key"],
            "strategy_type": strategy_type(proto),
            "operator_sequence": proto["operator_sequence"],
            "operator_family": proto["operator_family"],
            "step_count": proto["step_count"],
            "operand_count": proto["operand_count"],
            "normalized_program_template": proto["normalized_program_template"],
            "evidence_modality": proto["evidence_modality"],
            "scale_hint": proto["scale_hint"],
            "table_usage": {
                "multi_table_evidence": proto["table_usage"]["multi_table_evidence"],
                "has_hierarchy_markers": proto["table_usage"]["has_hierarchy_markers"],
            },
        },
        "representative_examples_redacted": group_examples(group["items"]),
        "strict_constraints": [
            "Do not solve any example.",
            "Do not include company names.",
            "Do not include concrete years.",
            "Do not include concrete numbers, table values, or numeric answers.",
            "Do not invent new formula or operator family.",
            "For program strategies, preserve the given operator/template and only explain general reasoning and evidence handling.",
            "For span strategies, describe lookup/comparison/superlative evidence behavior only.",
        ],
        "output_schema": LLM_SCHEMA,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def parse_llm_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]}")
    raw = json.loads(match.group(0))
    out = {"description": sanitize_text(raw.get("description", ""))}
    for key in [
        "reasoning_guidance",
        "evidence_guidance",
        "operand_roles",
        "scale_notes",
        "multi_table_notes",
        "risk_notes",
    ]:
        value = raw.get(key, [])
        if isinstance(value, str):
            value = [value]
        out[key] = [sanitize_text(x) for x in value if sanitize_text(x)]
    out["answer_form"] = sanitize_text(raw.get("answer_form", ""))
    return out


def sanitize_text(text: Any) -> str:
    text = normalize_space(text)
    text = re.sub(r"\b(?:19|20)\d{2}\b", "a reporting period", text)
    text = re.sub(r"\$\s*\d[\d,]*(?:\.\d+)?", "a monetary value", text)
    text = re.sub(r"\b\d{1,3}(?:,\d{3})+\b", "a numeric value", text)
    text = re.sub(r"\b\d+\.\d+\b", "a numeric value", text)
    text = re.sub(r"\b(?!0\b|1\b)\d+\b", "a numeric value", text)
    return normalize_space(text)


def llm_abstraction(group: dict[str, Any], cache: dict[str, dict[str, Any]], dry_run: bool = False) -> dict[str, Any]:
    prompt = prompt_for_group(group)
    key_payload = {
        "version": PILOT_VERSION,
        "runtime": llm.runtime_config(),
        "call_max_tokens": LLM_MAX_TOKENS,
        "call_temperature": 0,
        "system": SYSTEM,
        "prompt": prompt,
        "schema": LLM_SCHEMA,
    }
    key = stable_hash(key_payload)
    if key in cache:
        rec = dict(cache[key])
        rec["parsed"] = parse_llm_json(json.dumps(rec["parsed"], ensure_ascii=False))
        return rec
    if dry_run:
        raise RuntimeError(f"Missing cache for {group['group_key']} and dry_run=True")
    response = llm.call_once_with_metadata(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        max_tokens=LLM_MAX_TOKENS,
        temperature=0,
        timeout=180,
    )
    parsed = parse_llm_json(response["text"])
    rec = {
        "key": key,
        "group_key": group["group_key"],
        "strategy_level": group["level"],
        "prompt": prompt,
        "raw_response": response["text"],
        "parsed": parsed,
        "runtime": response.get("runtime", {}),
    }
    append_jsonl(CACHE_PATH, rec)
    cache[key] = rec
    return rec


def strategy_id(group: dict[str, Any]) -> str:
    return "multihiertt_strategy:" + stable_hash({
        "version": PILOT_VERSION,
        "level": group["level"],
        "group_key": group["group_key"],
    })[:16]


def retrieval_text(strategy: dict[str, Any]) -> str:
    parts = [
        f"Dataset: {strategy['dataset_id']}",
        f"Type: {strategy['strategy_type']}",
        f"Level: {strategy['strategy_level']}",
        f"Family: {strategy['family']}",
        f"Schema: {strategy['schema_key']}",
        f"Operators: {'>'.join(strategy['operator_sequence']) or 'none'}",
        f"Operator family: {strategy['operator_family']}",
        f"Formula template: {strategy['normalized_program_template']}",
        f"Evidence modality: {strategy['evidence_modality']}",
        f"Scale: {strategy['scale_hint']}",
        f"Description: {strategy['description']}",
        "Reasoning: " + " ; ".join(strategy["reasoning_guidance"]),
        "Evidence: " + " ; ".join(strategy["evidence_guidance"]),
        "Roles: " + " ; ".join(strategy["operand_roles"]),
        f"Answer form: {strategy['answer_form']}",
        "Scale notes: " + " ; ".join(strategy["scale_notes"]),
        "Table notes: " + " ; ".join(strategy["multi_table_notes"]),
        "Risks: " + " ; ".join(strategy["risk_notes"]),
    ]
    return "\n".join(parts)


def build_strategy(group: dict[str, Any], semantic: dict[str, Any], generation: dict[str, Any]) -> dict[str, Any]:
    proto = group["prototype"]
    source_ids = [item["abstraction"]["sample_id"] for item in group["items"][:30]]
    strategy = {
        "strategy_id": strategy_id(group),
        "dataset_id": "multihiertt",
        "version": PILOT_VERSION,
        "strategy_level": group["level"],
        "strategy_type": strategy_type(proto),
        "family": group["family"],
        "schema_key": group["schema_key"],
        "source_support_count": group["support_count"],
        "source_sample_ids": source_ids,
        "operator_sequence": proto["operator_sequence"],
        "operator_family": proto["operator_family"],
        "normalized_program_template": proto["normalized_program_template"],
        "evidence_modality": proto["evidence_modality"],
        "table_usage": {
            "table_count": proto["table_usage"]["table_count"],
            "evidence_table_count": proto["table_usage"]["evidence_table_count"],
            "multi_table_evidence": proto["table_usage"]["multi_table_evidence"],
            "has_hierarchy_markers": proto["table_usage"]["has_hierarchy_markers"],
            "hierarchy_marker_count": proto["table_usage"]["hierarchy_marker_count"],
        },
        "scale_hint": proto["scale_hint"],
        "representative_examples_redacted": group_examples(group["items"]),
        "description": semantic["description"],
        "reasoning_guidance": semantic["reasoning_guidance"],
        "evidence_guidance": semantic["evidence_guidance"],
        "operand_roles": semantic["operand_roles"],
        "answer_form": semantic["answer_form"],
        "scale_notes": semantic["scale_notes"],
        "multi_table_notes": semantic["multi_table_notes"],
        "risk_notes": semantic["risk_notes"],
        "generation": generation,
    }
    strategy["retrieval_text"] = retrieval_text(strategy)
    return strategy


def leak_hits(text: str) -> list[dict[str, str]]:
    hits = []
    for name, pattern in LEAK_PATTERNS.items():
        for m in pattern.finditer(text):
            token = m.group(0)
            if token in {"0", "1"}:
                continue
            hits.append({"type": name, "text": token})
    return hits


def qc(strategies: list[dict[str, Any]], total_train: int, groups: list[dict[str, Any]]) -> dict[str, Any]:
    legal = []
    leaks = []
    desc_counter = Counter()
    retrieval_counter = Counter()
    strategy_ids = Counter(s["strategy_id"] for s in strategies)
    for s in strategies:
        missing = sorted(REQUIRED_STRATEGY_KEYS - set(s))
        legal.append({"strategy_id": s.get("strategy_id"), "missing": missing, "ok": not missing})
        semantic_text = json.dumps({
            "description": s["description"],
            "reasoning_guidance": s["reasoning_guidance"],
            "evidence_guidance": s["evidence_guidance"],
            "operand_roles": s["operand_roles"],
            "answer_form": s["answer_form"],
            "scale_notes": s["scale_notes"],
            "multi_table_notes": s["multi_table_notes"],
            "risk_notes": s["risk_notes"],
            "representative_examples_redacted": s["representative_examples_redacted"],
        }, ensure_ascii=False)
        lh = leak_hits(semantic_text)
        if lh:
            leaks.append({"strategy_id": s["strategy_id"], "schema_key": s["schema_key"], "hits": lh[:10]})
        desc_counter[normalize_space(s["description"]).lower()] += 1
        retrieval_counter[normalize_space(s["retrieval_text"]).lower()] += 1
    covered_ids = set()
    for group in groups:
        for item in group["items"]:
            covered_ids.add(item["abstraction"]["sample_id"])
    return {
        "strategy_count": len(strategies),
        "schema_legal_rate": sum(x["ok"] for x in legal) / len(legal) if legal else 0.0,
        "schema_legal_failures": [x for x in legal if not x["ok"]],
        "leak_failure_count": len(leaks),
        "leak_failures": leaks,
        "duplicate_strategy_id_count": sum(v - 1 for v in strategy_ids.values() if v > 1),
        "duplicate_description_count": sum(v - 1 for v in desc_counter.values() if v > 1),
        "duplicate_retrieval_text_count": sum(v - 1 for v in retrieval_counter.values() if v > 1),
        "covered_unique_train_samples": len(covered_ids),
        "covered_unique_train_rate": len(covered_ids) / total_train if total_train else 0.0,
        "strategy_level_counts": dict(Counter(s["strategy_level"] for s in strategies)),
        "strategy_type_counts": dict(Counter(s["strategy_type"] for s in strategies)),
        "family_counts": dict(Counter(s["family"] for s in strategies)),
        "generation_counts": dict(Counter(s["generation"]["method"] for s in strategies)),
    }


def write_report(strategies: list[dict[str, Any]], audit: dict[str, Any]) -> None:
    q = audit["qc"]
    lines = [
        "# MultiHiertt Strategy Memory Pilot",
        "",
        "Date: 2026-08-17",
        "",
        "Scope: v0 small pilot only. Frozen deterministic family/schema from `multihiertt_strategy_structure_audit.py`; no reclustering, no retrieval audit, no four-arm experiment, no router.",
        "",
        "## Construction",
        "",
        f"- Strategy coverage rule: top-{TOP_COARSE_N} coarse families + top-{TOP_SCHEMA_N} fine schema keys from the frozen structure audit.",
        f"- Total strategies: {q['strategy_count']}.",
        f"- Strategy levels: `{q['strategy_level_counts']}`.",
        f"- Strategy types: `{q['strategy_type_counts']}`.",
        f"- Generation counts: `{q['generation_counts']}`.",
        f"- Unique train samples covered by selected groups: {q['covered_unique_train_samples']} / {audit['total_train']} ({q['covered_unique_train_rate']:.3f}).",
        f"- Planned LLM calls: {audit['planned_llm_group_count']} with budget <= {MAX_LLM_CALLS}.",
        f"- Calls made in latest run: {audit['llm_calls_made']}; cache hits: {audit['llm_cache_hits']}; cache records after run: {audit['llm_cache_record_count_after']}.",
        "",
        "Program strategies preserve deterministic operator sequence and normalized MultiHiertt DSL templates. The LLM only supplied reusable reasoning, evidence, scale, and multi-table guidance. Span strategies use LLM abstraction for lookup/comparison/superlative behavior.",
        "",
        "## LLM Safety Contract",
        "",
        "- Examples are structural and redacted: no raw question text, no paragraphs, no table text, no company names, no concrete years, no concrete numbers, no answers.",
        "- Prompts include only frozen family/schema metadata, operator/template structure, evidence modality, scale hint, table/hierarchy flags, and 4-6 structural examples.",
        "- The model is explicitly forbidden from solving examples or inventing new formula/family definitions.",
        f"- Raw cache path: `{os.path.relpath(CACHE_PATH, ROOT)}`. It is ignored by git; audit JSON records cache keys and runtime summary.",
        "",
        "## Offline QC",
        "",
        f"- Schema legal rate: {q['schema_legal_rate']:.3f}.",
        f"- Leak failures: {q['leak_failure_count']}.",
        f"- Duplicate strategy ids: {q['duplicate_strategy_id_count']}.",
        f"- Duplicate descriptions: {q['duplicate_description_count']}.",
        f"- Duplicate retrieval texts: {q['duplicate_retrieval_text_count']}.",
        "",
        "The leak scan checks generated semantic text and structural examples for concrete years, currency/large numeric values, decimals, and standalone numbers beyond trivial placeholders. It is conservative text QC, not proof of semantic anonymity.",
        "",
        "## Sample Strategies",
        "",
    ]
    for s in strategies[:12]:
        lines.extend([
            f"### {s['strategy_id']}",
            "",
            f"- level: `{s['strategy_level']}`",
            f"- type: `{s['strategy_type']}`",
            f"- family: `{s['family']}`",
            f"- schema: `{s['schema_key']}`",
            f"- support: {s['source_support_count']}",
            f"- operators: `{'>'.join(s['operator_sequence']) or 'none'}`",
            f"- template: `{s['normalized_program_template']}`",
            f"- description: {s['description']}",
            f"- reasoning: {'; '.join(s['reasoning_guidance'])}",
            f"- evidence: {'; '.join(s['evidence_guidance'])}",
            f"- risks: {'; '.join(s['risk_notes'])}",
            "",
        ])
    lines.extend([
        "## QC Interpretation",
        "",
        "The v0 pool is intentionally small and high-support. Coarse strategies provide broad recall over common reasoning families, while schema strategies retain evidence modality, table usage, scale hint, and step-count specificity for retrieval experiments.",
        "",
        "Known limitations:",
        "",
        "- The pool is not intended to cover the fine-schema long tail.",
        "- LLM semantic guidance is exploratory and must be validated by retrieval-only audit before any execution experiment.",
        "- The automatic leakage scan cannot detect every company/entity mention, but prompts do not expose raw company/report text.",
        "",
        "## Decision",
        "",
        f"Decision: `{audit['decision']}`.",
    ])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run(dry_run: bool = False) -> dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(DATA_OUT_DIR, exist_ok=True)
    rows = load_rows("train")
    structure_audit = load_json(STRUCTURE_AUDIT_JSON_PATH)
    groups = build_groups(rows, structure_audit)
    cache = load_jsonl_cache(CACHE_PATH)
    strategies = []
    used_cache_records = []
    llm_calls_made = 0
    llm_cache_hits = 0
    for group in groups:
        before = len(cache)
        rec = llm_abstraction(group, cache, dry_run=dry_run)
        if len(cache) == before:
            llm_cache_hits += 1
        else:
            llm_calls_made += 1
        generation = {
            "method": "llm_guidance_with_deterministic_structure",
            "llm_cache_key": rec["key"],
            "runtime": rec.get("runtime", {}),
        }
        used_cache_records.append({k: rec[k] for k in ["key", "group_key", "strategy_level", "prompt", "raw_response", "parsed", "runtime"]})
        strategies.append(build_strategy(group, rec["parsed"], generation))
    rewrite_jsonl(CACHE_PATH, used_cache_records)
    cache = load_jsonl_cache(CACHE_PATH)
    audit = {
        "version": PILOT_VERSION,
        "total_train": len(rows),
        "top_coarse_n": TOP_COARSE_N,
        "top_schema_n": TOP_SCHEMA_N,
        "llm_call_budget": MAX_LLM_CALLS,
        "planned_llm_group_count": len(groups),
        "planned_groups": [
            {
                "level": g["level"],
                "group_key": g["group_key"],
                "family": g["family"],
                "schema_key": g["schema_key"],
                "support": g["support_count"],
            }
            for g in groups
        ],
        "llm_calls_made": llm_calls_made,
        "llm_cache_hits": llm_cache_hits,
        "llm_cache_record_count_after": len(cache),
        "runtime_request": llm.runtime_config(),
        "qc": qc(strategies, len(rows), groups),
        "strategy_index": [
            {
                "strategy_id": s["strategy_id"],
                "level": s["strategy_level"],
                "strategy_type": s["strategy_type"],
                "family": s["family"],
                "schema_key": s["schema_key"],
                "support": s["source_support_count"],
                "generation_method": s["generation"]["method"],
                "llm_cache_key": s["generation"]["llm_cache_key"],
            }
            for s in strategies
        ],
    }
    audit["decision"] = (
        "READY FOR STRATEGY RETRIEVAL AUDIT"
        if audit["qc"]["schema_legal_rate"] == 1.0
        and audit["qc"]["leak_failure_count"] == 0
        and audit["qc"]["duplicate_strategy_id_count"] == 0
        else "REVISE STRATEGY MEMORY"
    )
    dump_json(MEMORY_PATH, strategies)
    dump_json(AUDIT_JSON_PATH, audit)
    write_report(strategies, audit)
    print(json.dumps({
        "strategies": len(strategies),
        "planned_llm_calls": len(groups),
        "llm_calls_made": llm_calls_made,
        "llm_cache_hits": llm_cache_hits,
        "covered_unique_train_rate": audit["qc"]["covered_unique_train_rate"],
        "schema_legal_rate": audit["qc"]["schema_legal_rate"],
        "leak_failures": audit["qc"]["leak_failure_count"],
        "decision": audit["decision"],
        "memory": os.path.relpath(MEMORY_PATH, ROOT),
        "report": os.path.relpath(REPORT_PATH, ROOT),
    }, indent=2))
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Require all LLM outputs to already be cached.")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
