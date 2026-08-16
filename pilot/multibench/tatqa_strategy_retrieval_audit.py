"""TAT-QA Strategy Memory v0 retrieval-only audit.

No LLM/API calls. This freezes the current 30-item strategy memory and compares
semantic-rich retrieval text against a deterministic schema-only ablation.
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
from tatqa_case_memory import make_retrieval_text  # noqa: E402
from tatqa_ingest import parse_split  # noqa: E402
from tatqa_strategy_structure_audit import abstract_record  # noqa: E402

DATA_DIR = os.path.join(ROOT, "data", "tatqa", "processed")
OUT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "tatqa")
MEMORY_PATH = os.path.join(DATA_DIR, "tatqa_strategy_memory_v0.json")
AUDIT_JSON_PATH = os.path.join(OUT_DIR, "tatqa_strategy_retrieval_audit.json")
REPORT_PATH = os.path.join(OUT_DIR, "TATQA_STRATEGY_RETRIEVAL_AUDIT.md")

TOP_K = 3
AUDIT_N = 120
SEED = 20260816
VARIANTS = ["semantic", "schema_only"]


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def schema_only_text(strategy: dict[str, Any]) -> str:
    return "\n".join([
        f"Type: {strategy['strategy_type']}",
        f"Family: {strategy['family']}",
        f"Schema: {strategy['schema_key']}",
        f"Evidence source: {strategy['answer_from']}",
        f"Scale: {strategy['scale']}",
    ])


def strategy_text(strategy: dict[str, Any], variant: str) -> str:
    if variant == "semantic":
        return strategy["retrieval_text"]
    if variant == "schema_only":
        return schema_only_text(strategy)
    raise ValueError(f"unknown variant: {variant}")


def fixed_dev_sample(dev: list[dict[str, Any]], n: int = AUDIT_N) -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    return rng.sample(dev, min(n, len(dev)))


def embed_strategies(strategies: list[dict[str, Any]], variant: str) -> np.ndarray:
    model = get_model()
    texts = [strategy_text(s, variant) for s in strategies]
    return model.encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True)


def retrieve(query_text: str, strategies: list[dict[str, Any]], emb: np.ndarray, k: int = TOP_K) -> list[dict[str, Any]]:
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
            "strategy_type": s["strategy_type"],
            "family": s["family"],
            "answer_from": s["answer_from"],
            "scale": s["scale"],
            "score": float(sims[int(i)]),
        })
    return hits


def gold_schema_in_memory(absr: dict[str, Any], memory_by_schema: dict[str, dict[str, Any]]) -> bool:
    return absr["schema_key"] in memory_by_schema


def compatibility(absr: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    gold_schema = absr["schema_key"]
    gold_type = absr["strategy_type"]
    gold_family = absr["family"]
    gold_source = absr["answer_from"]
    gold_scale = absr["scale"]
    return {
        "schema_top1": bool(hits and hits[0]["schema_key"] == gold_schema),
        "schema_topk": any(h["schema_key"] == gold_schema for h in hits),
        "type_top1": bool(hits and hits[0]["strategy_type"] == gold_type),
        "type_topk": any(h["strategy_type"] == gold_type for h in hits),
        "family_top1": bool(hits and hits[0]["family"] == gold_family),
        "family_topk": any(h["family"] == gold_family for h in hits),
        "answer_from_top1": bool(hits and hits[0]["answer_from"] == gold_source),
        "answer_from_topk": any(h["answer_from"] == gold_source for h in hits),
        "scale_top1": bool(hits and hits[0]["scale"] == gold_scale),
        "scale_topk": any(h["scale"] == gold_scale for h in hits),
    }


def evaluate_variant(
    variant: str,
    sample: list[dict[str, Any]],
    strategies: list[dict[str, Any]],
    emb: np.ndarray,
    memory_by_schema: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    counters = Counter()
    eligible_counters = Counter()
    by_type = defaultdict(Counter)
    records = []
    for rec in sample:
        absr = abstract_record(rec)
        eligible = gold_schema_in_memory(absr, memory_by_schema)
        query_text = make_retrieval_text(rec, memory_side=False)
        hits = retrieve(query_text, strategies, emb, k=TOP_K)
        comp = compatibility(absr, hits)
        for k, v in comp.items():
            counters[k] += int(v)
            if eligible:
                eligible_counters[k] += int(v)
        counters["n"] += 1
        if eligible:
            eligible_counters["n"] += 1
        by_type[absr["strategy_type"]]["n"] += 1
        by_type[absr["strategy_type"]]["eligible"] += int(eligible)
        for k, v in comp.items():
            by_type[absr["strategy_type"]][k] += int(v)
        records.append({
            "sample_id": rec["sample_id"],
            "question": rec["question"],
            "gold": {
                "schema_key": absr["schema_key"],
                "strategy_type": absr["strategy_type"],
                "family": absr["family"],
                "answer_from": absr["answer_from"],
                "scale": absr["scale"],
                "in_memory": eligible,
            },
            "compatibility": comp,
            "top_strategies": hits,
        })

    def rates(c: Counter) -> dict[str, float]:
        n = c["n"]
        return {
            "n": int(n),
            "schema_top1": c["schema_top1"] / n if n else 0.0,
            "schema_top3": c["schema_topk"] / n if n else 0.0,
            "type_top1": c["type_top1"] / n if n else 0.0,
            "type_top3": c["type_topk"] / n if n else 0.0,
            "family_top1": c["family_top1"] / n if n else 0.0,
            "family_top3": c["family_topk"] / n if n else 0.0,
            "answer_from_top1": c["answer_from_top1"] / n if n else 0.0,
            "answer_from_top3": c["answer_from_topk"] / n if n else 0.0,
            "scale_top1": c["scale_top1"] / n if n else 0.0,
            "scale_top3": c["scale_topk"] / n if n else 0.0,
        }

    return {
        "variant": variant,
        "overall": rates(counters),
        "eligible_only": rates(eligible_counters),
        "by_strategy_type": {
            k: rates(v) | {"eligible": int(v["eligible"])}
            for k, v in sorted(by_type.items())
        },
        "records": records,
    }


def summarize_examples(records: list[dict[str, Any]], limit: int = 5) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    correct = []
    wrong = []
    for rec in records:
        if not rec["gold"]["in_memory"]:
            continue
        item = {
            "sample_id": rec["sample_id"],
            "question": rec["question"],
            "gold_schema": rec["gold"]["schema_key"],
            "top1_schema": rec["top_strategies"][0]["schema_key"] if rec["top_strategies"] else None,
            "top1_score": rec["top_strategies"][0]["score"] if rec["top_strategies"] else None,
            "top3_schema": [h["schema_key"] for h in rec["top_strategies"]],
        }
        if rec["compatibility"]["schema_topk"] and len(correct) < limit:
            correct.append(item)
        if not rec["compatibility"]["schema_topk"] and len(wrong) < limit:
            wrong.append(item)
        if len(correct) >= limit and len(wrong) >= limit:
            break
    return correct, wrong


def write_report(audit: dict[str, Any]) -> None:
    semantic = audit["variants"]["semantic"]
    schema_only = audit["variants"]["schema_only"]
    s = semantic["overall"]
    b = schema_only["overall"]
    se = semantic["eligible_only"]
    be = schema_only["eligible_only"]
    delta_schema_top3 = se["schema_top3"] - be["schema_top3"]
    delta_type_top3 = s["type_top3"] - b["type_top3"]
    lines = [
        "# TAT-QA Strategy Retrieval Audit",
        "",
        "Date: 2026-08-16",
        "",
        "Scope: retrieval-only audit for frozen `tatqa_strategy_memory_v0.json`. No LLM/API calls, no strategy edits, no family changes, no four-arm execution, no router.",
        "",
        "## Setup",
        "",
        f"- Strategy memory: 30 frozen strategies.",
        f"- Retriever: same dense embedding model as FinQA pilot, `{config.EMBED_MODEL}` on `{config.EMBED_DEVICE}`.",
        f"- Top-k: {TOP_K}.",
        f"- Fixed dev sample: {audit['sample_n']} examples, seed `{SEED}`.",
        "- Target query text uses only inference-time visible question, paragraphs, and table via `tatqa_case_memory.make_retrieval_text(..., memory_side=False)`.",
        "- Gold schema/type/source/scale are used only after retrieval for diagnostics.",
        "",
        "## Coverage",
        "",
        f"- Gold schema present in frozen memory for {audit['eligible_n']} / {audit['sample_n']} dev samples ({audit['eligible_rate']:.3f}).",
        "- Samples outside this coverage cannot have exact schema hit by construction; type/family/source/scale diagnostics are still reported.",
        "",
        "## Retrieval-Text Ablation",
        "",
        "| Variant | Exact schema top1 | Exact schema top3 | Type top1 | Type top3 | Family top3 | Source top3 | Scale top3 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        f"| Semantic-rich, all samples | {s['schema_top1']:.3f} | {s['schema_top3']:.3f} | {s['type_top1']:.3f} | {s['type_top3']:.3f} | {s['family_top3']:.3f} | {s['answer_from_top3']:.3f} | {s['scale_top3']:.3f} |",
        f"| Schema-only, all samples | {b['schema_top1']:.3f} | {b['schema_top3']:.3f} | {b['type_top1']:.3f} | {b['type_top3']:.3f} | {b['family_top3']:.3f} | {b['answer_from_top3']:.3f} | {b['scale_top3']:.3f} |",
        f"| Semantic-rich, eligible only | {se['schema_top1']:.3f} | {se['schema_top3']:.3f} | {se['type_top1']:.3f} | {se['type_top3']:.3f} | {se['family_top3']:.3f} | {se['answer_from_top3']:.3f} | {se['scale_top3']:.3f} |",
        f"| Schema-only, eligible only | {be['schema_top1']:.3f} | {be['schema_top3']:.3f} | {be['type_top1']:.3f} | {be['type_top3']:.3f} | {be['family_top3']:.3f} | {be['answer_from_top3']:.3f} | {be['scale_top3']:.3f} |",
        "",
        f"Semantic-rich minus schema-only exact schema top3 on eligible samples: {delta_schema_top3:+.3f}.",
        f"Semantic-rich minus schema-only strategy-type top3 on all samples: {delta_type_top3:+.3f}.",
        "",
        "## By Strategy Type",
        "",
        "| Type | N | Eligible | Semantic schema top3 | Schema-only schema top3 | Semantic type top3 | Schema-only type top3 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for t in sorted(semantic["by_strategy_type"]):
        st = semantic["by_strategy_type"][t]
        bt = schema_only["by_strategy_type"].get(t, {})
        lines.append(
            f"| `{t}` | {st['n']} | {st['eligible']} | {st['schema_top3']:.3f} | "
            f"{bt.get('schema_top3', 0.0):.3f} | {st['type_top3']:.3f} | {bt.get('type_top3', 0.0):.3f} |"
        )
    lines.extend([
        "",
        "## Typical Correct Retrievals",
        "",
    ])
    for ex in audit["examples"]["semantic_correct"]:
        lines.extend([
            f"- `{ex['sample_id']}`: gold `{ex['gold_schema']}`; top3 `{ex['top3_schema']}`; question: {ex['question'][:180]}",
        ])
    lines.extend([
        "",
        "## Typical Errors",
        "",
    ])
    for ex in audit["examples"]["semantic_wrong"]:
        lines.extend([
            f"- `{ex['sample_id']}`: gold `{ex['gold_schema']}`; top1 `{ex['top1_schema']}`; top3 `{ex['top3_schema']}`; question: {ex['question'][:180]}",
        ])
    improves = delta_schema_top3 > 0.02 or delta_type_top3 > 0.02
    lines.extend([
        "",
        "## Interpretation",
        "",
        ("Semantic abstraction improves retrieval alignment over schema-only metadata in this fixed audit." if improves else "Semantic abstraction does not clearly improve retrieval alignment over schema-only metadata in this fixed audit."),
        "",
        "Main failure modes:",
        "",
        "- Frozen v0 covers only top-30 train schema families, so exact schema retrieval is impossible for out-of-memory dev schemas.",
        "- Dense retrieval sometimes overweights semantic surface cues such as lookup/comparison wording and misses source/scale-specific schema variants.",
        "- Arithmetic strategy families are schema-heavy; natural language question/context similarity can retrieve a nearby arithmetic family but wrong source or scale.",
        "- The current target query includes full context, which can add evidence text that pulls toward lookup strategies even when the gold schema is arithmetic.",
        "",
        "## Decision",
        "",
        ("Decision: `FREEZE FOR TAT-QA FOUR-ARM SMALL DRY-RUN`." if improves and se["schema_top3"] >= 0.35 else "Decision: `NEEDS STRATEGY RETRIEVAL REVISION BEFORE FOUR-ARM DRY-RUN`."),
    ])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run() -> dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True)
    strategies = load_json(MEMORY_PATH)
    memory_by_schema = {s["schema_key"]: s for s in strategies}
    dev = parse_split("dev")
    sample = fixed_dev_sample(dev, AUDIT_N)
    abstractions = [abstract_record(rec) for rec in sample]
    eligible_n = sum(1 for a in abstractions if a["schema_key"] in memory_by_schema)
    embeddings = {variant: embed_strategies(strategies, variant) for variant in VARIANTS}
    variants = {
        variant: evaluate_variant(variant, sample, strategies, embeddings[variant], memory_by_schema)
        for variant in VARIANTS
    }
    correct, wrong = summarize_examples(variants["semantic"]["records"])
    audit = {
        "sample_n": len(sample),
        "seed": SEED,
        "top_k": TOP_K,
        "strategy_count": len(strategies),
        "eligible_n": eligible_n,
        "eligible_rate": eligible_n / len(sample) if sample else 0.0,
        "retriever": {
            "model": config.EMBED_MODEL,
            "device": config.EMBED_DEVICE,
            "query_text_builder": "tatqa_case_memory.make_retrieval_text(memory_side=False)",
        },
        "variants": variants,
        "examples": {
            "semantic_correct": correct,
            "semantic_wrong": wrong,
        },
    }
    dump_json(AUDIT_JSON_PATH, audit)
    write_report(audit)
    print(json.dumps({
        "sample_n": audit["sample_n"],
        "eligible_n": eligible_n,
        "semantic_schema_top3_eligible": variants["semantic"]["eligible_only"]["schema_top3"],
        "schema_only_schema_top3_eligible": variants["schema_only"]["eligible_only"]["schema_top3"],
        "semantic_type_top3": variants["semantic"]["overall"]["type_top3"],
        "schema_only_type_top3": variants["schema_only"]["overall"]["type_top3"],
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
