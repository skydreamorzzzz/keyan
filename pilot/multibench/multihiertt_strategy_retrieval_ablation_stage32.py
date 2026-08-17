"""MultiHiertt Strategy Retrieval Ablation — Stage 32.

Scientific question: Does query representation richness (full-context vs question-only)
or candidate crowding (multiple pool entries per family) better explain the
family_top3=0.216 failure from Stage 31?

2×2 factorial (no LLM calls):
  Rows: question_only vs full_context
  Cols: raw_top3 (positions 1-3 from top-10) vs dedup_top3 (family-dedup of top-10)

Same frozen 32-strategy memory, same 120-sample validation set (seed 20260817).
"""
from __future__ import annotations

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
JSON_PATH = os.path.join(OUT_DIR, "multihiertt_strategy_retrieval_ablation_stage32.json")
REPORT_PATH = os.path.join(OUT_DIR, "MULTIHIERTT_STRATEGY_RETRIEVAL_ABLATION_STAGE32.md")

TOP_K_EXPAND = 10  # retrieve top-10; derive top-3 raw and top-3 dedup from it
AUDIT_N = 120
SEED = 20260817
QUERY_VARIANTS = ["question_only", "full_context"]
RANKING_VARIANTS = ["raw_top3", "dedup_top3"]


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def question_only_text(row: dict[str, Any]) -> str:
    return row.get("question", "")


def full_context_text(row: dict[str, Any]) -> str:
    return make_target_retrieval_text(row)


def build_query_text(row: dict[str, Any], variant: str) -> str:
    if variant == "question_only":
        return question_only_text(row)
    if variant == "full_context":
        return full_context_text(row)
    raise ValueError(f"unknown query variant: {variant}")


def embed_strategies(strategies: list[dict[str, Any]]) -> np.ndarray:
    model = get_model()
    texts = [s["retrieval_text"] for s in strategies]
    return model.encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True)


def retrieve_topk(
    query_text: str,
    strategies: list[dict[str, Any]],
    emb: np.ndarray,
    k: int = TOP_K_EXPAND,
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


def family_dedup_top3(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep best-scoring hit per family; return top-3 distinct families."""
    seen: dict[str, dict[str, Any]] = {}
    for h in hits:
        fam = h["family"]
        if fam not in seen or h["score"] > seen[fam]["score"]:
            seen[fam] = h
    by_score = sorted(seen.values(), key=lambda x: -x["score"])
    return by_score[:3]


def raw_top3(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return hits[:3]


def compatibility(absr: dict[str, Any], top3_hits: list[dict[str, Any]]) -> dict[str, Any]:
    gold_family = absr["family"]
    gold_type = strategy_type_label(absr)
    gold_schema = absr["schema_key"]
    return {
        "family_top1": bool(top3_hits and top3_hits[0]["family"] == gold_family),
        "family_topk": any(h["family"] == gold_family for h in top3_hits),
        "type_top1": bool(top3_hits and top3_hits[0]["strategy_type"] == gold_type),
        "type_topk": any(h["strategy_type"] == gold_type for h in top3_hits),
        "exact_schema_topk": any(h["schema_key"] == gold_schema for h in top3_hits),
    }


def rates(c: Counter) -> dict[str, float]:
    n = c["n"]
    if not n:
        return {"n": 0, "family_top1": 0.0, "family_top3": 0.0, "type_top3": 0.0, "exact_schema_top3": 0.0}
    return {
        "n": int(n),
        "family_top1": c["family_top1"] / n,
        "family_top3": c["family_topk"] / n,
        "type_top1": c["type_top1"] / n,
        "type_top3": c["type_topk"] / n,
        "exact_schema_top3": c["exact_schema_topk"] / n,
    }


def fixed_validation_sample(rows: list[dict[str, Any]], n: int = AUDIT_N) -> list[tuple[int, dict[str, Any]]]:
    rng = random.Random(SEED)
    indexed = list(enumerate(rows))
    return rng.sample(indexed, min(n, len(indexed)))


def evaluate_cell(
    sample: list[tuple[int, dict[str, Any]]],
    strategies: list[dict[str, Any]],
    emb: np.ndarray,
    pool_families: set[str],
    schema_level_schemas: set[str],
    query_variant: str,
    ranking_variant: str,
) -> dict[str, Any]:
    counters = Counter()
    eligible_counters = Counter()
    by_type: dict[str, Counter] = defaultdict(Counter)
    records = []

    for index, row in sample:
        absr = abstract_record(row, index)
        fam_eligible = absr["family"] in pool_families
        schema_eligible = absr["schema_key"] in schema_level_schemas

        query_text = build_query_text(row, query_variant)
        top10 = retrieve_topk(query_text, strategies, emb, k=TOP_K_EXPAND)

        if ranking_variant == "raw_top3":
            top3 = raw_top3(top10)
        else:
            top3 = family_dedup_top3(top10)

        comp = compatibility(absr, top3)
        distinct_families_in_top3 = len({h["family"] for h in top3})

        for key, val in comp.items():
            counters[key] += int(val)
            if fam_eligible:
                eligible_counters[key] += int(val)
        counters["n"] += 1
        if fam_eligible:
            eligible_counters["n"] += 1

        stype = strategy_type_label(absr)
        by_type[stype]["n"] += 1
        by_type[stype]["family_eligible"] += int(fam_eligible)
        for key, val in comp.items():
            by_type[stype][key] += int(val)

        records.append({
            "sample_id": f"multihiertt:validation:{row.get('uid') or index}",
            "question": row.get("question", ""),
            "gold_family": absr["family"],
            "gold_type": strategy_type_label(absr),
            "family_eligible": fam_eligible,
            "schema_eligible": schema_eligible,
            "distinct_families_in_top3": distinct_families_in_top3,
            "top3_families": [h["family"] for h in top3],
            "top3_scores": [round(h["score"], 4) for h in top3],
            "family_top1": comp["family_top1"],
            "family_topk": comp["family_topk"],
            "type_topk": comp["type_topk"],
        })

    return {
        "query_variant": query_variant,
        "ranking_variant": ranking_variant,
        "overall": rates(counters),
        "eligible_only": rates(eligible_counters),
        "by_strategy_type": {
            t: rates(c) | {"family_eligible": int(c["family_eligible"])}
            for t, c in sorted(by_type.items())
        },
        "records": records,
    }


def crowding_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyse how often top-3 slots are dominated by a single family (raw top3)."""
    prog = [r for r in records if r["gold_type"] == "program"]
    if not prog:
        return {}
    single_fam = sum(1 for r in prog if r["distinct_families_in_top3"] == 1)
    two_fam = sum(1 for r in prog if r["distinct_families_in_top3"] == 2)
    three_fam = sum(1 for r in prog if r["distinct_families_in_top3"] == 3)

    # Which families dominate top1 in failing program queries
    top1_in_failing = Counter(
        r["top3_families"][0]
        for r in prog
        if not r["family_topk"] and r["top3_families"]
    )
    return {
        "program_n": len(prog),
        "distinct_fam_in_top3": {"1": single_fam, "2": two_fam, "3": three_fam},
        "top1_family_failing": dict(top1_in_failing.most_common(8)),
    }


def run() -> dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True)
    strategies = load_json(MEMORY_PATH)
    pool_families = {s["family"] for s in strategies}
    schema_level_schemas = {s["schema_key"] for s in strategies if s["strategy_level"] == "schema"}

    val_rows = load_rows("validation")
    sample = fixed_validation_sample(val_rows, AUDIT_N)

    family_eligible_n = sum(
        1 for idx, row in sample
        if abstract_record(row, idx)["family"] in pool_families
    )

    print(f"Building embeddings (semantic)…")
    emb = embed_strategies(strategies)

    print(f"Evaluating 2×2 factorial…")
    cells: dict[str, dict[str, Any]] = {}
    for qv in QUERY_VARIANTS:
        for rv in RANKING_VARIANTS:
            key = f"{qv}__{rv}"
            print(f"  {key}…")
            cells[key] = evaluate_cell(
                sample, strategies, emb, pool_families, schema_level_schemas, qv, rv
            )

    # Crowding diagnostic: from raw_top3 with full_context (Stage 31 baseline)
    baseline_records = cells["full_context__raw_top3"]["records"]
    crowding = crowding_stats(baseline_records)

    # Crowding diagnostic: from raw_top3 with question_only
    qonly_records = cells["question_only__raw_top3"]["records"]
    crowding_qonly = crowding_stats(qonly_records)

    # Summary table
    summary = {}
    for qv in QUERY_VARIANTS:
        for rv in RANKING_VARIANTS:
            key = f"{qv}__{rv}"
            cell = cells[key]
            summary[key] = {
                "family_top3_eligible": cell["eligible_only"]["family_top3"],
                "family_top3_all": cell["overall"]["family_top3"],
                "type_top3_all": cell["overall"]["type_top3"],
            }

    # Stage 32 decision
    best_key = max(summary, key=lambda k: summary[k]["family_top3_eligible"])
    best_val = summary[best_key]["family_top3_eligible"]
    if best_val >= 0.45:
        decision = f"PROCEED_WITH_{best_key.upper()}_TO_STAGE33_HYDE"
    elif best_val >= 0.35:
        decision = f"MARGINAL_{best_key.upper()}_CONSIDER_HYDE"
    else:
        decision = "INTRINSIC_CEILING_NEEDS_STRUCTURAL_QUERY_AUGMENTATION"

    audit = {
        "stage": 32,
        "sample_n": AUDIT_N,
        "seed": SEED,
        "top_k_expand": TOP_K_EXPAND,
        "strategy_count": len(strategies),
        "family_eligible_n": family_eligible_n,
        "query_variants": QUERY_VARIANTS,
        "ranking_variants": RANKING_VARIANTS,
        "summary": summary,
        "crowding_full_context_raw": crowding,
        "crowding_question_only_raw": crowding_qonly,
        "cells": cells,
        "best_condition": best_key,
        "best_family_top3_eligible": best_val,
        "decision": decision,
    }

    dump_json(JSON_PATH, audit)
    write_report(audit)

    print(json.dumps({
        "stage": 32,
        "summary": summary,
        "best_condition": best_key,
        "best_family_top3_eligible": round(best_val, 4),
        "decision": decision,
        "report": os.path.relpath(REPORT_PATH, ROOT),
        "json": os.path.relpath(JSON_PATH, ROOT),
    }, indent=2))
    return audit


def write_report(audit: dict[str, Any]) -> None:
    summary = audit["summary"]
    cells = audit["cells"]
    crowding = audit["crowding_full_context_raw"]

    lines = [
        "# MultiHiertt Strategy Retrieval Ablation — Stage 32",
        "",
        "Date: 2026-08-17",
        "",
        "## Scientific question",
        "",
        "Does query representation richness (full context vs question-only) or candidate crowding",
        "(multiple pool entries per family) better explain the family_top3=0.216 failure",
        "from Stage 31?",
        "",
        "## Setup",
        "",
        f"- Same frozen 32-strategy memory as Stage 31.",
        f"- Same 120-sample validation set (seed 20260817).",
        f"- Expanded top-k = {audit['top_k_expand']} to enable family-deduplicated ranking.",
        f"- family_eligible_n = {audit['family_eligible_n']} / {audit['sample_n']}.",
        f"- Query variants: question_only (question text only) vs full_context (Stage 31 baseline).",
        f"- Ranking variants: raw_top3 (positions 1-3) vs dedup_top3 (family-deduplicated top-3 from top-10).",
        "",
        "## 2×2 Summary (family top3, family-eligible samples)",
        "",
        "| | raw_top3 | dedup_top3 | delta_dedup |",
        "|---|---:|---:|---:|",
    ]
    for qv in ["question_only", "full_context"]:
        raw = summary[f"{qv}__raw_top3"]["family_top3_eligible"]
        dedup = summary[f"{qv}__dedup_top3"]["family_top3_eligible"]
        delta = dedup - raw
        lines.append(f"| {qv} | {raw:.3f} | {dedup:.3f} | {delta:+.3f} |")

    # Delta query representation
    raw_fc = summary["full_context__raw_top3"]["family_top3_eligible"]
    raw_qo = summary["question_only__raw_top3"]["family_top3_eligible"]
    dedup_fc = summary["full_context__dedup_top3"]["family_top3_eligible"]
    dedup_qo = summary["question_only__dedup_top3"]["family_top3_eligible"]

    lines.extend([
        "",
        f"- Delta query (question_only − full_context), raw: {raw_qo - raw_fc:+.3f}",
        f"- Delta query (question_only − full_context), dedup: {dedup_qo - dedup_fc:+.3f}",
        f"- Delta dedup (dedup − raw), full_context: {dedup_fc - raw_fc:+.3f}",
        f"- Delta dedup (dedup − raw), question_only: {dedup_qo - raw_qo:+.3f}",
        "",
        "## All-sample type_top3",
        "",
        "| | raw_top3 | dedup_top3 |",
        "|---|---:|---:|",
    ])
    for qv in ["question_only", "full_context"]:
        raw = summary[f"{qv}__raw_top3"]["type_top3_all"]
        dedup = summary[f"{qv}__dedup_top3"]["type_top3_all"]
        lines.append(f"| {qv} | {raw:.3f} | {dedup:.3f} |")

    lines.extend([
        "",
        "## Per-type breakdown: question_only raw_top3",
        "",
        "| Type | N | Fam-elig | family_top3 | type_top3 |",
        "|---|---:|---:|---:|---:|",
    ])
    qo_cell = cells["question_only__raw_top3"]
    for t, st in sorted(qo_cell["by_strategy_type"].items()):
        lines.append(
            f"| `{t}` | {st['n']} | {st['family_eligible']} | "
            f"{st['family_top3']:.3f} | {st['type_top3']:.3f} |"
        )

    lines.extend([
        "",
        "## Per-type breakdown: full_context dedup_top3",
        "",
        "| Type | N | Fam-elig | family_top3 | type_top3 |",
        "|---|---:|---:|---:|---:|",
    ])
    fc_dedup_cell = cells["full_context__dedup_top3"]
    for t, st in sorted(fc_dedup_cell["by_strategy_type"].items()):
        lines.append(
            f"| `{t}` | {st['n']} | {st['family_eligible']} | "
            f"{st['family_top3']:.3f} | {st['type_top3']:.3f} |"
        )

    lines.extend([
        "",
        "## Crowding Diagnostic (full_context, raw_top3, program queries only)",
        "",
        f"- program_n: {crowding.get('program_n', 0)}",
    ])
    dist = crowding.get("distinct_fam_in_top3", {})
    lines.append(
        f"- distinct families in top3: 1={dist.get('1',0)}, 2={dist.get('2',0)}, 3={dist.get('3',0)}"
    )
    top1f = crowding.get("top1_family_failing", {})
    lines.append(f"- families dominating top1 in failing program queries: {dict(list(top1f.items())[:5])}")

    lines.extend([
        "",
        "## Decision",
        "",
        f"Best condition: `{audit['best_condition']}` with family_top3_eligible = {audit['best_family_top3_eligible']:.3f}.",
        f"Decision: `{audit['decision']}`.",
    ])

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    run()
