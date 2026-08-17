"""MultiHiertt Strategy Memory v0 retrieval-only audit.

No LLM/API calls. Frozen 32-strategy memory. Compares semantic-rich retrieval
text against a schema-only metadata ablation on a fixed validation sample.
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
from multihiertt_case_memory import make_target_retrieval_text  # noqa: E402
from multihiertt_strategy_memory_pilot import strategy_type as strategy_type_label  # noqa: E402
from multihiertt_strategy_structure_audit import abstract_record, load_rows  # noqa: E402

DATA_DIR = os.path.join(ROOT, "data", "multihiertt", "processed")
OUT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "multihiertt")
MEMORY_PATH = os.path.join(DATA_DIR, "multihiertt_strategy_memory_v0.json")
AUDIT_JSON_PATH = os.path.join(OUT_DIR, "multihiertt_strategy_retrieval_audit.json")
REPORT_PATH = os.path.join(OUT_DIR, "MULTIHIERTT_STRATEGY_RETRIEVAL_AUDIT.md")

TOP_K = 3
AUDIT_N = 120
SEED = 20260817
VARIANTS = ["semantic", "schema_only"]


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def table_bucket_for_strategy(strategy: dict[str, Any]) -> str:
    usage = strategy["table_usage"]
    if usage.get("multi_table_evidence"):
        return "multi"
    # strategy stores evidence_table_count; has_table_evidence is not saved
    if usage.get("evidence_table_count", 0) > 0:
        return "single"
    return "none"


def schema_only_text(strategy: dict[str, Any]) -> str:
    ops = ">".join(strategy["operator_sequence"]) if strategy["operator_sequence"] else "none"
    return "\n".join([
        f"Type: {strategy['strategy_type']}",
        f"Family: {strategy['family']}",
        f"Schema: {strategy['schema_key']}",
        f"Level: {strategy['strategy_level']}",
        f"Operators: {ops}",
        f"Template: {strategy['normalized_program_template'] or 'none'}",
        f"Evidence: {strategy['evidence_modality']}",
        f"Tables: {table_bucket_for_strategy(strategy)}",
        f"Scale: {strategy['scale_hint']}",
    ])


def strategy_text(strategy: dict[str, Any], variant: str) -> str:
    if variant == "semantic":
        return strategy["retrieval_text"]
    if variant == "schema_only":
        return schema_only_text(strategy)
    raise ValueError(f"unknown variant: {variant}")


def fixed_validation_sample(rows: list[dict[str, Any]], n: int = AUDIT_N) -> list[tuple[int, dict[str, Any]]]:
    rng = random.Random(SEED)
    indexed = list(enumerate(rows))
    return rng.sample(indexed, min(n, len(indexed)))


def embed_strategies(strategies: list[dict[str, Any]], variant: str) -> np.ndarray:
    model = get_model()
    texts = [strategy_text(s, variant) for s in strategies]
    return model.encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True)


def retrieve(
    query_text: str,
    strategies: list[dict[str, Any]],
    emb: np.ndarray,
    k: int = TOP_K,
) -> list[dict[str, Any]]:
    model = get_model()
    q = model.encode([query_text], normalize_embeddings=True)[0]
    sims = emb @ q
    idx = np.argsort(-sims)[:k]
    hits = []
    for i in idx:
        s = strategies[int(i)]
        hits.append({
            "strategy_id": s["strategy_id"],
            "schema_key": s["schema_key"],
            "family": s["family"],
            "strategy_type": s["strategy_type"],
            "strategy_level": s["strategy_level"],
            "evidence_modality": s["evidence_modality"],
            "scale_hint": s["scale_hint"],
            "multi_table": bool(s["table_usage"].get("multi_table_evidence", False)),
            "score": float(sims[int(i)]),
        })
    return hits


def gold_family_in_pool(absr: dict[str, Any], pool_families: set[str]) -> bool:
    return absr["family"] in pool_families


def gold_schema_in_pool(absr: dict[str, Any], schema_level_schemas: set[str]) -> bool:
    return absr["schema_key"] in schema_level_schemas


def compatibility(absr: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    gold_family = absr["family"]
    gold_type = strategy_type_label(absr)
    gold_schema = absr["schema_key"]
    gold_evidence = absr["evidence_modality"]
    gold_scale = absr["scale_hint"]
    gold_multi_table = absr["table_usage"]["multi_table_evidence"]
    return {
        "family_top1": bool(hits and hits[0]["family"] == gold_family),
        "family_topk": any(h["family"] == gold_family for h in hits),
        "type_top1": bool(hits and hits[0]["strategy_type"] == gold_type),
        "type_topk": any(h["strategy_type"] == gold_type for h in hits),
        "exact_schema_top1": bool(hits and hits[0]["schema_key"] == gold_schema),
        "exact_schema_topk": any(h["schema_key"] == gold_schema for h in hits),
        "evidence_top1": bool(hits and hits[0]["evidence_modality"] == gold_evidence),
        "evidence_topk": any(h["evidence_modality"] == gold_evidence for h in hits),
        "scale_top1": bool(hits and hits[0]["scale_hint"] == gold_scale),
        "scale_topk": any(h["scale_hint"] == gold_scale for h in hits),
        "multi_table_top1": bool(hits and hits[0]["multi_table"] == gold_multi_table),
        "multi_table_topk": any(h["multi_table"] == gold_multi_table for h in hits),
    }


def rates(c: Counter) -> dict[str, float]:
    n = c["n"]
    return {
        "n": int(n),
        "family_top1": c["family_top1"] / n if n else 0.0,
        "family_top3": c["family_topk"] / n if n else 0.0,
        "type_top1": c["type_top1"] / n if n else 0.0,
        "type_top3": c["type_topk"] / n if n else 0.0,
        "exact_schema_top1": c["exact_schema_top1"] / n if n else 0.0,
        "exact_schema_top3": c["exact_schema_topk"] / n if n else 0.0,
        "evidence_top1": c["evidence_top1"] / n if n else 0.0,
        "evidence_top3": c["evidence_topk"] / n if n else 0.0,
        "scale_top1": c["scale_top1"] / n if n else 0.0,
        "scale_top3": c["scale_topk"] / n if n else 0.0,
        "multi_table_top1": c["multi_table_top1"] / n if n else 0.0,
        "multi_table_top3": c["multi_table_topk"] / n if n else 0.0,
    }


def evaluate_variant(
    variant: str,
    sample: list[tuple[int, dict[str, Any]]],
    strategies: list[dict[str, Any]],
    emb: np.ndarray,
    pool_families: set[str],
    schema_level_schemas: set[str],
) -> dict[str, Any]:
    counters = Counter()
    family_eligible_counters = Counter()
    schema_eligible_counters = Counter()
    by_type: dict[str, Counter] = defaultdict(Counter)
    records = []

    for index, row in sample:
        absr = abstract_record(row, index)
        fam_eligible = gold_family_in_pool(absr, pool_families)
        schema_eligible = gold_schema_in_pool(absr, schema_level_schemas)
        query_text = make_target_retrieval_text(row)
        hits = retrieve(query_text, strategies, emb, k=TOP_K)
        comp = compatibility(absr, hits)

        for key, val in comp.items():
            counters[key] += int(val)
            if fam_eligible:
                family_eligible_counters[key] += int(val)
            if schema_eligible:
                schema_eligible_counters[key] += int(val)
        counters["n"] += 1
        if fam_eligible:
            family_eligible_counters["n"] += 1
        if schema_eligible:
            schema_eligible_counters["n"] += 1

        stype = strategy_type_label(absr)
        by_type[stype]["n"] += 1
        by_type[stype]["family_eligible"] += int(fam_eligible)
        by_type[stype]["schema_eligible"] += int(schema_eligible)
        for key, val in comp.items():
            by_type[stype][key] += int(val)

        records.append({
            "sample_id": f"multihiertt:validation:{row.get('uid') or index}",
            "question": row.get("question", ""),
            "gold": {
                "family": absr["family"],
                "schema_key": absr["schema_key"],
                "strategy_type": strategy_type_label(absr),
                "evidence_modality": absr["evidence_modality"],
                "scale_hint": absr["scale_hint"],
                "multi_table": absr["table_usage"]["multi_table_evidence"],
                "family_eligible": fam_eligible,
                "schema_eligible": schema_eligible,
            },
            "compatibility": comp,
            "top_strategies": hits,
        })

    return {
        "variant": variant,
        "overall": rates(counters),
        "family_eligible_only": rates(family_eligible_counters),
        "schema_eligible_only": rates(schema_eligible_counters),
        "by_strategy_type": {
            t: rates(c) | {"family_eligible": int(c["family_eligible"]), "schema_eligible": int(c["schema_eligible"])}
            for t, c in sorted(by_type.items())
        },
        "records": records,
    }


def summarize_examples(records: list[dict[str, Any]], limit: int = 5) -> dict[str, Any]:
    correct: list[dict[str, Any]] = []
    wrong: list[dict[str, Any]] = []
    for rec in records:
        if not rec["gold"]["family_eligible"]:
            continue
        item = {
            "sample_id": rec["sample_id"],
            "question": rec["question"][:200],
            "gold_family": rec["gold"]["family"],
            "gold_schema": rec["gold"]["schema_key"],
            "gold_type": rec["gold"]["strategy_type"],
            "top1_family": rec["top_strategies"][0]["family"] if rec["top_strategies"] else None,
            "top3_families": [h["family"] for h in rec["top_strategies"]],
            "top1_score": rec["top_strategies"][0]["score"] if rec["top_strategies"] else None,
        }
        if rec["compatibility"]["family_topk"] and len(correct) < limit:
            correct.append(item)
        if not rec["compatibility"]["family_topk"] and len(wrong) < limit:
            wrong.append(item)
        if len(correct) >= limit and len(wrong) >= limit:
            break
    return {"semantic_correct": correct, "semantic_wrong": wrong}


def choose_decision(sem: dict[str, Any]) -> str:
    family_top3_eligible = sem["family_eligible_only"]["family_top3"]
    type_top3_all = sem["overall"]["type_top3"]
    if family_top3_eligible >= 0.65 and type_top3_all >= 0.60:
        return "READY FOR STRATEGY QUERY METHOD AUDIT (HYDE/REWRITE)"
    return "NEEDS RETRIEVAL REVISION BEFORE FOUR-ARM DRY-RUN"


def write_report(audit: dict[str, Any]) -> None:
    sem = audit["variants"]["semantic"]
    sch = audit["variants"]["schema_only"]
    s_all = sem["overall"]
    b_all = sch["overall"]
    s_fam = sem["family_eligible_only"]
    b_fam = sch["family_eligible_only"]
    s_sch = sem["schema_eligible_only"]
    b_sch = sch["schema_eligible_only"]
    delta_family_top3 = s_fam["family_top3"] - b_fam["family_top3"]
    delta_type_top3 = s_all["type_top3"] - b_all["type_top3"]
    decision = audit["decision"]

    lines = [
        "# MultiHiertt Strategy Retrieval Audit",
        "",
        "Date: 2026-08-17",
        "",
        "Scope: retrieval-only audit for frozen `multihiertt_strategy_memory_v0.json` (32 strategies). "
        "No LLM/API calls, no strategy edits, no family changes, no four-arm execution, no router.",
        "",
        "## Setup",
        "",
        f"- Strategy memory: {audit['strategy_count']} frozen strategies "
        f"({audit['coarse_count']} coarse-level + {audit['schema_count']} schema-level).",
        f"- Retriever: `{config.EMBED_MODEL}` on `{config.EMBED_DEVICE}`.",
        f"- Top-k: {TOP_K}.",
        f"- Fixed validation sample: {audit['sample_n']} examples, seed `{SEED}` "
        "(same seed as Case Memory audit, ensures consistency).",
        "- Target query text uses only inference-visible fields: question, paragraphs, hierarchical HTML table "
        "previews, table descriptions via `multihiertt_case_memory.make_target_retrieval_text()`.",
        "- Gold family/type/schema/evidence/scale/multi_table used only after retrieval for post-hoc diagnostics.",
        "",
        "## Pool Coverage",
        "",
        f"- Gold family present in frozen pool (12 coarse families): "
        f"{audit['family_eligible_n']} / {audit['sample_n']} ({audit['family_eligible_rate']:.3f}).",
        f"- Gold fine schema_key present in schema-level pool (20 schemas): "
        f"{audit['schema_eligible_n']} / {audit['sample_n']} ({audit['schema_eligible_rate']:.3f}).",
        "- Primary eligibility gate is family-level (coarse pool covers top families). "
        "Exact schema eligibility is lower by design (top-20 covers ~50% of train schema distribution).",
        "",
        "## Retrieval Ablation: All Samples",
        "",
        "| Variant | Family top1 | Family top3 | Type top1 | Type top3 | Exact schema top3 | Evidence top3 | Scale top3 | Multi-table top3 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| Semantic-rich | {s_all['family_top1']:.3f} | {s_all['family_top3']:.3f} | "
        f"{s_all['type_top1']:.3f} | {s_all['type_top3']:.3f} | {s_all['exact_schema_top3']:.3f} | "
        f"{s_all['evidence_top3']:.3f} | {s_all['scale_top3']:.3f} | {s_all['multi_table_top3']:.3f} |",
        f"| Schema-only | {b_all['family_top1']:.3f} | {b_all['family_top3']:.3f} | "
        f"{b_all['type_top1']:.3f} | {b_all['type_top3']:.3f} | {b_all['exact_schema_top3']:.3f} | "
        f"{b_all['evidence_top3']:.3f} | {b_all['scale_top3']:.3f} | {b_all['multi_table_top3']:.3f} |",
        "",
        "## Retrieval Ablation: Family-Eligible Only",
        "",
        "| Variant | Family top1 | Family top3 | Type top3 | Exact schema top3 | Evidence top3 | Scale top3 |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| Semantic-rich | {s_fam['family_top1']:.3f} | {s_fam['family_top3']:.3f} | "
        f"{s_fam['type_top3']:.3f} | {s_fam['exact_schema_top3']:.3f} | "
        f"{s_fam['evidence_top3']:.3f} | {s_fam['scale_top3']:.3f} |",
        f"| Schema-only | {b_fam['family_top1']:.3f} | {b_fam['family_top3']:.3f} | "
        f"{b_fam['type_top3']:.3f} | {b_fam['exact_schema_top3']:.3f} | "
        f"{b_fam['evidence_top3']:.3f} | {b_fam['scale_top3']:.3f} |",
        "",
        "## Retrieval Ablation: Schema-Eligible Only",
        "",
        "| Variant | Family top3 | Type top3 | Exact schema top1 | Exact schema top3 | Evidence top3 | Scale top3 |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| Semantic-rich | {s_sch['family_top3']:.3f} | {s_sch['type_top3']:.3f} | "
        f"{s_sch['exact_schema_top1']:.3f} | {s_sch['exact_schema_top3']:.3f} | "
        f"{s_sch['evidence_top3']:.3f} | {s_sch['scale_top3']:.3f} |",
        f"| Schema-only | {b_sch['family_top3']:.3f} | {b_sch['type_top3']:.3f} | "
        f"{b_sch['exact_schema_top1']:.3f} | {b_sch['exact_schema_top3']:.3f} | "
        f"{b_sch['evidence_top3']:.3f} | {b_sch['scale_top3']:.3f} |",
        "",
        f"Semantic minus schema-only family top3 (family-eligible): {delta_family_top3:+.3f}.",
        f"Semantic minus schema-only type top3 (all samples): {delta_type_top3:+.3f}.",
        "",
        "## By Strategy Type",
        "",
        "| Type | N | Fam-elig | Sch-elig | Sem family top3 | Sch-only family top3 | Sem type top3 | Sch-only type top3 | Sem exact schema top3 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for t in sorted(sem["by_strategy_type"]):
        st = sem["by_strategy_type"][t]
        bt = sch["by_strategy_type"].get(t, {})
        lines.append(
            f"| `{t}` | {st['n']} | {st['family_eligible']} | {st['schema_eligible']} | "
            f"{st['family_top3']:.3f} | {bt.get('family_top3', 0.0):.3f} | "
            f"{st['type_top3']:.3f} | {bt.get('type_top3', 0.0):.3f} | "
            f"{st['exact_schema_top3']:.3f} |"
        )
    lines.extend([
        "",
        "## Typical Correct Retrievals",
        "",
    ])
    for ex in audit["examples"]["semantic_correct"]:
        lines.append(
            f"- `{ex['sample_id']}`: gold `{ex['gold_family']}`; top3 families `{ex['top3_families']}`; "
            f"question: {ex['question'][:180]}"
        )
    lines.extend([
        "",
        "## Typical Errors",
        "",
    ])
    for ex in audit["examples"]["semantic_wrong"]:
        lines.append(
            f"- `{ex['sample_id']}`: gold `{ex['gold_family']}`; top1 `{ex['top1_family']}`; "
            f"top3 families `{ex['top3_families']}`; question: {ex['question'][:180]}"
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
    ])
    if delta_family_top3 > 0.03:
        lines.append(
            "Semantic abstraction improves family retrieval alignment over schema-only metadata "
            f"by {delta_family_top3:+.3f} family top3 on family-eligible samples."
        )
    elif delta_family_top3 < -0.03:
        lines.append(
            "Semantic abstraction hurts family retrieval alignment compared to schema-only metadata "
            f"by {delta_family_top3:+.3f} family top3 on family-eligible samples."
        )
    else:
        lines.append(
            "Semantic abstraction provides roughly equivalent family retrieval alignment to schema-only metadata "
            f"({delta_family_top3:+.3f} family top3 on family-eligible samples)."
        )
    lines.extend([
        "",
        "Main failure modes:",
        "",
        "- Dense retrieval may overweight surface semantic cues and miss structural schema distinctions "
        "(evidence modality, table count, scale hint).",
        "- Coarse strategies for the same answer type (all program families) are semantically similar, "
        "making fine-grained disambiguation challenging without query reformulation.",
        "- Multi-table evidence queries may retrieve single-table strategies when the question wording "
        "does not explicitly reference multiple tables.",
        "- Span strategy types (superlative, comparison) may be confused by program-like arithmetic language "
        "in MultiHiertt questions.",
        "- The frozen v0 pool covers only top families, so some dev samples' families are out-of-pool.",
        "",
        "## Decision",
        "",
        f"Decision: `{decision}`.",
        "",
        f"Primary metric: semantic-rich family top3 on family-eligible samples = {s_fam['family_top3']:.3f}.",
        f"Type top3 all samples = {s_all['type_top3']:.3f}.",
        f"Exact schema top3 on schema-eligible samples = {s_sch['exact_schema_top3']:.3f}.",
    ])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run() -> dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True)
    strategies = load_json(MEMORY_PATH)
    pool_families = {s["family"] for s in strategies}
    schema_level_schemas = {s["schema_key"] for s in strategies if s["strategy_level"] == "schema"}

    val_rows = load_rows("validation")
    sample = fixed_validation_sample(val_rows, AUDIT_N)

    family_eligible_n = sum(
        1 for idx, row in sample
        if gold_family_in_pool(abstract_record(row, idx), pool_families)
    )
    schema_eligible_n = sum(
        1 for idx, row in sample
        if gold_schema_in_pool(abstract_record(row, idx), schema_level_schemas)
    )

    embeddings = {v: embed_strategies(strategies, v) for v in VARIANTS}
    variants = {
        v: evaluate_variant(v, sample, strategies, embeddings[v], pool_families, schema_level_schemas)
        for v in VARIANTS
    }
    examples = summarize_examples(variants["semantic"]["records"])
    decision = choose_decision(variants["semantic"])

    audit = {
        "sample_n": len(sample),
        "seed": SEED,
        "top_k": TOP_K,
        "strategy_count": len(strategies),
        "coarse_count": sum(1 for s in strategies if s["strategy_level"] == "coarse"),
        "schema_count": sum(1 for s in strategies if s["strategy_level"] == "schema"),
        "family_eligible_n": family_eligible_n,
        "family_eligible_rate": family_eligible_n / len(sample) if sample else 0.0,
        "schema_eligible_n": schema_eligible_n,
        "schema_eligible_rate": schema_eligible_n / len(sample) if sample else 0.0,
        "retriever": {
            "model": config.EMBED_MODEL,
            "device": config.EMBED_DEVICE,
            "query_text_builder": "multihiertt_case_memory.make_target_retrieval_text()",
        },
        "variants": variants,
        "examples": examples,
        "decision": decision,
    }
    dump_json(AUDIT_JSON_PATH, audit)
    write_report(audit)

    sem = variants["semantic"]
    sch = variants["schema_only"]
    print(json.dumps({
        "sample_n": audit["sample_n"],
        "family_eligible_n": family_eligible_n,
        "schema_eligible_n": schema_eligible_n,
        "semantic_family_top3_all": sem["overall"]["family_top3"],
        "semantic_family_top3_family_eligible": sem["family_eligible_only"]["family_top3"],
        "schema_only_family_top3_family_eligible": sch["family_eligible_only"]["family_top3"],
        "semantic_type_top3_all": sem["overall"]["type_top3"],
        "semantic_exact_schema_top3_schema_eligible": sem["schema_eligible_only"]["exact_schema_top3"],
        "delta_family_top3_eligible": sem["family_eligible_only"]["family_top3"] - sch["family_eligible_only"]["family_top3"],
        "decision": decision,
        "report": os.path.relpath(REPORT_PATH, ROOT),
        "json": os.path.relpath(AUDIT_JSON_PATH, ROOT),
    }, indent=2))
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
