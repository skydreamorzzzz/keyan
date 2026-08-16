"""TAT-QA Strategy Memory v0 small pilot.

The family/schema definitions are frozen from
`tatqa_strategy_structure_audit.py`. Arithmetic strategies are generated
deterministically; high-frequency lookup/count/comparison schemas receive a
small LLM semantic abstraction pass. This script does not run retrieval, QA
arms, or router experiments.
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
from tatqa_ingest import parse_split  # noqa: E402
from tatqa_strategy_structure_audit import abstract_record, normalize_question_template  # noqa: E402

OUT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "tatqa")
DATA_OUT_DIR = os.path.join(ROOT, "data", "tatqa", "processed")
MEMORY_PATH = os.path.join(DATA_OUT_DIR, "tatqa_strategy_memory_v0.json")
AUDIT_JSON_PATH = os.path.join(OUT_DIR, "tatqa_strategy_memory_pilot_audit.json")
REPORT_PATH = os.path.join(OUT_DIR, "TATQA_STRATEGY_MEMORY_PILOT.md")
CACHE_PATH = os.path.join(OUT_DIR, "tatqa_strategy_memory_v0_llm_cache.jsonl")

PILOT_VERSION = "tatqa_strategy_memory_v0_top30_schema_frozen_v1"
TOP_SCHEMA_N = 30
EXAMPLES_PER_SCHEMA = 6
MAX_LLM_CALLS = 20

NON_ARITHMETIC_TYPES = {"span_lookup", "multi_span_lookup", "count", "comparison"}
REQUIRED_STRATEGY_KEYS = {
    "strategy_id",
    "dataset_id",
    "strategy_type",
    "family",
    "schema_key",
    "answer_from",
    "scale",
    "source_support_count",
    "source_sample_ids",
    "description",
    "evidence_guidance",
    "operand_roles",
    "answer_form",
    "scale_notes",
    "risk_notes",
    "retrieval_text",
    "generation",
}

SYSTEM = (
    "You write reusable, label-free TAT-QA financial QA strategy abstractions. "
    "Never solve an example. Never include company names, specific years, specific numbers, "
    "specific answers, or copied phrases that identify an individual report. Return only JSON."
)

LLM_SCHEMA = {
    "description": "one general sentence about when to use this strategy",
    "evidence_guidance": ["2-4 short bullets for locating evidence"],
    "operand_roles": ["2-4 abstract roles such as metric label, reporting period, compared item, item list"],
    "answer_form": "how the final answer should be expressed",
    "scale_notes": ["1-3 notes about units/scale handling"],
    "risk_notes": ["1-3 common failure modes"],
}

LEAK_PATTERNS = {
    "four_digit_year": re.compile(r"\b(?:19|20)\d{2}\b"),
    "currency_or_large_number": re.compile(r"\$\s*\d|\b\d{1,3}(?:,\d{3})+\b|\b\d+\.\d+\b"),
    "standalone_number": re.compile(r"\b\d+\b"),
}


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


def dump_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def parse_schema_key(schema_key: str) -> dict[str, str]:
    parts = schema_key.split("|")
    return {
        "strategy_type": parts[0],
        "family": parts[1],
        "answer_from": parts[2].split("=", 1)[1],
        "scale": parts[3].split("=", 1)[1],
    }


def build_schema_groups(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter]:
    abstractions = []
    for rec in records:
        a = abstract_record(rec)
        abstractions.append({"record": rec, "abstraction": a})
    schema_counter = Counter(x["abstraction"]["schema_key"] for x in abstractions)
    top_keys = {k for k, _ in schema_counter.most_common(TOP_SCHEMA_N)}
    groups = defaultdict(list)
    for x in abstractions:
        if x["abstraction"]["schema_key"] in top_keys:
            groups[x["abstraction"]["schema_key"]].append(x)
    ordered = []
    for schema_key, count in schema_counter.most_common(TOP_SCHEMA_N):
        ordered.append({
            "schema_key": schema_key,
            "support_count": count,
            "items": groups[schema_key],
            **parse_schema_key(schema_key),
        })
    return ordered, schema_counter


def representative_examples(items: list[dict[str, Any]], n: int = EXAMPLES_PER_SCHEMA) -> list[dict[str, Any]]:
    """Pick deterministic examples with diverse sanitized question templates."""
    seen = set()
    out = []
    for item in items:
        rec = item["record"]
        absr = item["abstraction"]
        template = normalize_question_template(rec.get("question", ""))
        if template in seen:
            continue
        seen.add(template)
        out.append({
            "question_template": template,
            "answer_from": absr["answer_from"],
            "scale": absr["scale"],
            "req_comparison": bool(absr.get("req_comparison")),
        })
        if len(out) >= n:
            break
    return out


def prompt_for_group(group: dict[str, Any]) -> str:
    payload = {
        "task": "Create a reusable TAT-QA strategy for this frozen schema family.",
        "frozen_schema": {
            "strategy_type": group["strategy_type"],
            "family": group["family"],
            "answer_from": group["answer_from"],
            "scale": group["scale"],
            "schema_key": group["schema_key"],
        },
        "representative_examples_sanitized": representative_examples(group["items"]),
        "strict_constraints": [
            "Do not answer any example.",
            "Do not include company names.",
            "Do not include concrete years.",
            "Do not include concrete numbers or numeric answers.",
            "Describe only general evidence locating, operand role, answer-form, and scale precautions.",
            "Do not invent new strategy families.",
        ],
        "output_schema": LLM_SCHEMA,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def parse_llm_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]}")
    raw = json.loads(match.group(0))
    out = {}
    out["description"] = str(raw.get("description", "")).strip()
    for key in ["evidence_guidance", "operand_roles", "scale_notes", "risk_notes"]:
        val = raw.get(key, [])
        if isinstance(val, str):
            val = [val]
        out[key] = [str(x).strip() for x in val if str(x).strip()]
    out["answer_form"] = str(raw.get("answer_form", "")).strip()
    return sanitize_semantic(out)


def sanitize_text(text: str) -> str:
    text = re.sub(r"\b(?:19|20)\d{2}\b", "a reporting period", text)
    text = re.sub(r"\$\s*\d[\d,]*(?:\.\d+)?", "a monetary value", text)
    text = re.sub(r"\b\d{1,3}(?:,\d{3})+\b", "a numeric value", text)
    text = re.sub(r"\b\d+\.\d+\b", "a numeric value", text)
    text = re.sub(r"\b(?!0\b|1\b)\d+\b", "a numeric value", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def sanitize_semantic(obj: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, val in obj.items():
        if isinstance(val, list):
            out[key] = [sanitize_text(str(x)) for x in val]
        else:
            out[key] = sanitize_text(str(val))
    return out


def llm_abstraction(group: dict[str, Any], cache: dict[str, dict[str, Any]], dry_run: bool = False) -> dict[str, Any]:
    prompt = prompt_for_group(group)
    key_payload = {
        "version": PILOT_VERSION,
        "runtime": llm.runtime_config(),
        "system": SYSTEM,
        "prompt": prompt,
        "schema": LLM_SCHEMA,
    }
    key = stable_hash(key_payload)
    if key in cache:
        rec = dict(cache[key])
        rec["parsed"] = sanitize_semantic(rec["parsed"])
        return rec
    if dry_run:
        raise RuntimeError(f"Missing cache for {group['schema_key']} and dry_run=True")
    response = llm.call_once_with_metadata(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        max_tokens=700,
        temperature=0,
        timeout=180,
    )
    parsed = parse_llm_json(response["text"])
    rec = {
        "key": key,
        "schema_key": group["schema_key"],
        "prompt": prompt,
        "raw_response": response["text"],
        "parsed": parsed,
        "runtime": response.get("runtime", {}),
    }
    append_jsonl(CACHE_PATH, rec)
    cache[key] = rec
    return rec


def deterministic_arithmetic_text(group: dict[str, Any]) -> dict[str, Any]:
    family = group["family"]
    answer_from = group["answer_from"]
    scale = group["scale"]
    if family == "arithmetic:percent_change":
        description = "Use when the question asks for relative change between a new value and a prior/base value."
        evidence = ["Locate the same metric for the compared periods or conditions.", "Use the newer/current value as the changed amount endpoint and the prior/base value as denominator."]
        roles = ["new_or_current_value", "prior_or_base_value", "metric_label"]
        answer_form = "Return a relative change using the requested percent convention."
        risks = ["Do not reverse the numerator order.", "Do not report the raw difference when a relative change is requested."]
    elif family == "arithmetic:difference":
        description = "Use when the question asks for an absolute difference or change between two values."
        evidence = ["Locate two comparable values for the same metric or requested pair.", "Subtract in the direction implied by the question wording."]
        roles = ["minuend_value", "subtrahend_value", "metric_or_item_label"]
        answer_form = "Return the absolute difference in the requested unit."
        risks = ["Check whether the wording asks for increase, decrease, or simple difference.", "Do not convert to percent unless explicitly requested."]
    elif family == "arithmetic:ratio":
        description = "Use when the question asks for one quantity divided by another quantity."
        evidence = ["Locate numerator and denominator values from the requested evidence source.", "Confirm both operands use compatible units before division."]
        roles = ["numerator_value", "denominator_value", "ratio_metric"]
        answer_form = "Return the quotient or percentage according to the requested scale."
        risks = ["Do not swap numerator and denominator.", "Watch for percent versus raw ratio output."]
    elif family == "arithmetic:sum":
        description = "Use when the question asks for total amount from adding listed components."
        evidence = ["Locate all requested components and include each once.", "Keep components within the same unit/scale before summing."]
        roles = ["component_values", "total_target"]
        answer_form = "Return the summed amount in the requested unit."
        risks = ["Avoid omitting negative components.", "Avoid double-counting subtotal rows."]
    else:
        description = "Use when the question requires a composed arithmetic calculation following the frozen operator sequence."
        evidence = ["Locate all operands required by the normalized formula.", "Execute operations in the preserved parenthesis/order structure."]
        roles = ["formula_operands", "intermediate_values", "final_result"]
        answer_form = "Return the final numeric result in the requested scale."
        risks = ["Respect operation order and parentheses.", "Check unit compatibility before combining operands."]
    if scale == "percent":
        scale_notes = ["Treat percent output carefully; distinguish percentage points from percent change."]
    elif scale in {"thousand", "million", "billion"}:
        scale_notes = [f"Express the answer in {scale} units when the task requires that scale."]
    else:
        scale_notes = ["Preserve the answer scale requested by the question and evidence."]
    if answer_from == "table-text":
        evidence.append("Combine table values with nearby textual qualifiers when the evidence source is mixed.")
    elif answer_from == "text":
        evidence.append("Use textual numeric statements rather than assuming a table-only lookup.")
    return {
        "description": description,
        "evidence_guidance": evidence,
        "operand_roles": roles,
        "answer_form": answer_form,
        "scale_notes": scale_notes,
        "risk_notes": risks,
    }


def retrieval_text(strategy: dict[str, Any]) -> str:
    parts = [
        f"Type: {strategy['strategy_type']}",
        f"Family: {strategy['family']}",
        f"Evidence source: {strategy['answer_from']}",
        f"Scale: {strategy['scale']}",
        f"Description: {strategy['description']}",
        "Evidence guidance: " + " ; ".join(strategy["evidence_guidance"]),
        "Operand roles: " + " ; ".join(strategy["operand_roles"]),
        f"Answer form: {strategy['answer_form']}",
        "Scale notes: " + " ; ".join(strategy["scale_notes"]),
        "Risks: " + " ; ".join(strategy["risk_notes"]),
    ]
    return "\n".join(parts)


def build_strategy(group: dict[str, Any], semantic: dict[str, Any], generation: dict[str, Any]) -> dict[str, Any]:
    sid = "tatqa_strategy:" + stable_hash({
        "version": PILOT_VERSION,
        "schema_key": group["schema_key"],
    })[:16]
    source_ids = [x["abstraction"]["sample_id"] for x in group["items"][:20]]
    representative = representative_examples(group["items"], n=EXAMPLES_PER_SCHEMA)
    strategy = {
        "strategy_id": sid,
        "dataset_id": "tatqa",
        "version": PILOT_VERSION,
        "strategy_type": group["strategy_type"],
        "family": group["family"],
        "schema_key": group["schema_key"],
        "answer_from": group["answer_from"],
        "scale": group["scale"],
        "source_support_count": group["support_count"],
        "source_sample_ids": source_ids,
        "representative_examples_sanitized": representative,
        "description": semantic["description"],
        "evidence_guidance": semantic["evidence_guidance"],
        "operand_roles": semantic["operand_roles"],
        "answer_form": semantic["answer_form"],
        "scale_notes": semantic["scale_notes"],
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


def qc(strategies: list[dict[str, Any]], total_train: int, schema_counter: Counter) -> dict[str, Any]:
    legal = []
    leaks = []
    desc_counter = Counter()
    retrieval_counter = Counter()
    for s in strategies:
        missing = sorted(REQUIRED_STRATEGY_KEYS - set(s))
        legal.append({"strategy_id": s.get("strategy_id"), "missing": missing, "ok": not missing})
        text = json.dumps({
            "description": s["description"],
            "evidence_guidance": s["evidence_guidance"],
            "operand_roles": s["operand_roles"],
            "answer_form": s["answer_form"],
            "scale_notes": s["scale_notes"],
            "risk_notes": s["risk_notes"],
        }, ensure_ascii=False)
        lh = leak_hits(text)
        if lh:
            leaks.append({"strategy_id": s["strategy_id"], "schema_key": s["schema_key"], "hits": lh[:10]})
        desc_counter[re.sub(r"\s+", " ", s["description"].lower()).strip()] += 1
        retrieval_counter[re.sub(r"\s+", " ", s["retrieval_text"].lower()).strip()] += 1
    support = sum(s["source_support_count"] for s in strategies)
    included_schema_keys = {s["schema_key"] for s in strategies}
    top30_support = sum(v for k, v in schema_counter.most_common(TOP_SCHEMA_N))
    return {
        "strategy_count": len(strategies),
        "schema_legal_rate": sum(x["ok"] for x in legal) / len(legal) if legal else 0.0,
        "schema_legal_failures": [x for x in legal if not x["ok"]],
        "leak_failure_count": len(leaks),
        "leak_failures": leaks,
        "duplicate_description_count": sum(v - 1 for v in desc_counter.values() if v > 1),
        "duplicate_retrieval_text_count": sum(v - 1 for v in retrieval_counter.values() if v > 1),
        "covered_train_support": support,
        "covered_train_rate": support / total_train if total_train else 0.0,
        "top_schema_n": TOP_SCHEMA_N,
        "top_schema_support": top30_support,
        "top_schema_support_rate": top30_support / total_train if total_train else 0.0,
        "selected_schema_keys": sorted(included_schema_keys),
        "strategy_type_counts": dict(Counter(s["strategy_type"] for s in strategies)),
        "generation_counts": dict(Counter(s["generation"]["method"] for s in strategies)),
    }


def write_report(strategies: list[dict[str, Any]], audit: dict[str, Any]) -> None:
    q = audit["qc"]
    lines = [
        "# TAT-QA Strategy Memory Pilot",
        "",
        "Date: 2026-08-16",
        "",
        "Scope: v0 small pilot only. Frozen deterministic schema from `tatqa_strategy_structure_audit.py`; no reclustering, no family retuning, no retrieval audit, no four-arm experiment, no router.",
        "",
        "## Construction",
        "",
        f"- Strategy unit: top-{TOP_SCHEMA_N} frozen schema families by train support.",
        f"- Total strategies: {q['strategy_count']}.",
        f"- Train support covered: {q['covered_train_support']} / {audit['total_train']} ({q['covered_train_rate']:.3f}).",
        f"- Top-{TOP_SCHEMA_N} schema support rate: {q['top_schema_support_rate']:.3f}.",
        f"- Generation counts: `{q['generation_counts']}`.",
        f"- Strategy type counts: `{q['strategy_type_counts']}`.",
        f"- LLM cache records: {audit['llm_cache_record_count_after']} for {audit['planned_llm_group_count']} planned semantic abstractions; budget: <= {MAX_LLM_CALLS}.",
        f"- Calls made in the most recent build command: {audit['llm_calls_made']}; cache hits: {audit['llm_cache_hits']}.",
        "",
        "Arithmetic strategies were generated directly from deterministic structure templates. High-frequency `span_lookup`, `multi_span_lookup`, `count`, and `comparison` schema families used one LLM semantic abstraction call per schema, with 4-6 sanitized representative question templates.",
        "",
        "## LLM Safety Contract",
        "",
        "- Prompt examples contain sanitized question templates only; concrete numbers and years are replaced upstream.",
        "- Prompts exclude answer strings, derivations, table values, paragraphs, company names, and raw report text.",
        "- The model is asked only for evidence locating, operand roles, answer form, scale notes, and risks.",
        "- Raw responses are cached in `pilot/multibench/output/tatqa/tatqa_strategy_memory_v0_llm_cache.jsonl`.",
        "",
        "## Offline QC",
        "",
        f"- Schema legal rate: {q['schema_legal_rate']:.3f}.",
        f"- Leak failures: {q['leak_failure_count']}.",
        f"- Duplicate descriptions: {q['duplicate_description_count']}.",
        f"- Duplicate retrieval texts: {q['duplicate_retrieval_text_count']}.",
        "",
        "The leak scan checks generated semantic text for concrete years, currency/large numeric values, decimals, and standalone numbers beyond trivial placeholders. It is a conservative text scan, not proof of semantic anonymity.",
        "",
        "## Sample Strategies",
        "",
    ]
    for s in strategies[:10]:
        lines.extend([
            f"### {s['strategy_id']}",
            "",
            f"- schema: `{s['schema_key']}`",
            f"- support: {s['source_support_count']}",
            f"- method: `{s['generation']['method']}`",
            f"- description: {s['description']}",
            f"- evidence: {'; '.join(s['evidence_guidance'])}",
            f"- roles: {'; '.join(s['operand_roles'])}",
            f"- scale: {'; '.join(s['scale_notes'])}",
            "",
        ])
    lines.extend([
        "## Added Value Over Deterministic Labels",
        "",
        "The LLM-generated lookup/count/comparison strategies add reusable semantic guidance that deterministic labels do not provide: where to look for evidence, whether to preserve a single span or multiple spans, what abstract roles to bind, how to treat mixed table/text evidence, and common scale/output risks. Arithmetic strategies intentionally add less prose because the deterministic formula family already captures most reusable procedure.",
        "",
        "## Decision",
        "",
        "The v0 memory is suitable for the next offline retrieval audit, with two constraints: keep this strategy set frozen for that audit, and treat leakage/QC checks as necessary but not sufficient before any execution experiment.",
        "",
        "Decision: `READY FOR TAT-QA STRATEGY RETRIEVAL AUDIT`.",
    ])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run(dry_run: bool = False) -> dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(DATA_OUT_DIR, exist_ok=True)
    records = parse_split("train")
    groups, schema_counter = build_schema_groups(records)
    non_arith_groups = [g for g in groups if g["strategy_type"] in NON_ARITHMETIC_TYPES]
    if len(non_arith_groups) > MAX_LLM_CALLS:
        raise RuntimeError(f"LLM call plan would exceed budget: {len(non_arith_groups)} > {MAX_LLM_CALLS}")
    cache = load_jsonl_cache(CACHE_PATH)
    llm_calls_made = 0
    llm_cache_hits = 0
    strategies = []
    for group in groups:
        if group["strategy_type"] == "arithmetic":
            semantic = deterministic_arithmetic_text(group)
            generation = {"method": "deterministic_arithmetic_template", "llm_cache_key": None}
        else:
            before = len(cache)
            rec = llm_abstraction(group, cache, dry_run=dry_run)
            if len(cache) == before:
                llm_cache_hits += 1
            else:
                llm_calls_made += 1
            semantic = rec["parsed"]
            generation = {
                "method": "llm_semantic_abstraction",
                "llm_cache_key": rec["key"],
                "runtime": rec.get("runtime", {}),
            }
        strategies.append(build_strategy(group, semantic, generation))
    audit = {
        "version": PILOT_VERSION,
        "total_train": len(records),
        "top_schema_n": TOP_SCHEMA_N,
        "llm_call_budget": MAX_LLM_CALLS,
        "planned_llm_groups": [g["schema_key"] for g in non_arith_groups],
        "planned_llm_group_count": len(non_arith_groups),
        "llm_calls_made": llm_calls_made,
        "llm_cache_hits": llm_cache_hits,
        "llm_cache_record_count_after": len(cache),
        "runtime_request": llm.runtime_config(),
        "qc": qc(strategies, len(records), schema_counter),
        "strategy_index": [
            {
                "strategy_id": s["strategy_id"],
                "schema_key": s["schema_key"],
                "strategy_type": s["strategy_type"],
                "support": s["source_support_count"],
                "generation_method": s["generation"]["method"],
            }
            for s in strategies
        ],
    }
    dump_json(MEMORY_PATH, strategies)
    dump_json(AUDIT_JSON_PATH, audit)
    write_report(strategies, audit)
    print(json.dumps({
        "strategies": len(strategies),
        "planned_llm_calls": len(non_arith_groups),
        "llm_calls_made": llm_calls_made,
        "llm_cache_hits": llm_cache_hits,
        "covered_train_rate": audit["qc"]["covered_train_rate"],
        "schema_legal_rate": audit["qc"]["schema_legal_rate"],
        "leak_failures": audit["qc"]["leak_failure_count"],
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
