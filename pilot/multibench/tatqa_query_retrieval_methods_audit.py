"""TAT-QA Strategy retrieval query-method audit.

Compares question-only semantic retrieval with LLM query rewriting and HyDE.
The Strategy Memory, dev sample, embedding model, and top-k are frozen.
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

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PILOT_DIR = os.path.join(ROOT, "pilot")
if PILOT_DIR not in sys.path:
    sys.path.insert(0, PILOT_DIR)
if os.path.dirname(__file__) not in sys.path:
    sys.path.insert(0, os.path.dirname(__file__))

import config  # noqa: E402
import llm  # noqa: E402
from retrieval import get_model  # noqa: E402
from tatqa_ingest import parse_split  # noqa: E402
from tatqa_strategy_retrieval_audit import (  # noqa: E402
    AUDIT_N,
    MEMORY_PATH,
    SEED,
    TOP_K,
    compatibility,
    fixed_dev_sample,
    gold_schema_in_memory,
    load_json,
    retrieve,
)
from tatqa_strategy_structure_audit import abstract_record  # noqa: E402

OUT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "tatqa")
AUDIT_JSON_PATH = os.path.join(OUT_DIR, "tatqa_query_retrieval_methods_audit.json")
REPORT_PATH = os.path.join(OUT_DIR, "TATQA_QUERY_RETRIEVAL_METHODS_AUDIT.md")
CACHE_PATH = os.path.join(OUT_DIR, "tatqa_query_retrieval_methods_cache.jsonl")

METHOD_VERSION = "tatqa_query_retrieval_methods_v1_frozen_strategy_memory"
METHODS = ["question_only", "query_rewrite", "hyde"]

SYSTEM = (
    "You rewrite TAT-QA questions for retrieving reusable reasoning strategies. "
    "Do not answer the question. Do not infer or mention any gold label. "
    "Return only valid JSON."
)


def dump_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def normalize_generated_text(text: str) -> str:
    text = re.sub(r"\b(?:19|20)\d{2}\b", "reporting period", text)
    text = re.sub(r"\$\s*\d[\d,]*(?:\.\d+)?", "monetary value", text)
    text = re.sub(r"\b\d{1,3}(?:,\d{3})+\b", "numeric value", text)
    text = re.sub(r"\b\d+\.\d+\b", "numeric value", text)
    text = re.sub(r"\b(?!0\b|1\b)\d+\b", "numeric value", text)
    return re.sub(r"\s+", " ", text).strip()


def prompt_for_question(question: str) -> str:
    payload = {
        "task": "Generate two retrieval queries for matching this question to a reusable TAT-QA reasoning strategy.",
        "question": question,
        "constraints": [
            "Use only the question text.",
            "Do not solve the question.",
            "Do not mention a final answer.",
            "Do not use or guess gold answer_type, scale, operator, derivation, or schema labels.",
            "Abstract away company names, concrete years, and concrete numeric values when possible.",
            "Focus on reasoning intent, evidence source clues, operand roles, answer form, and unit/scale risk.",
        ],
        "output_json_schema": {
            "query_rewrite": "one concise strategy-retrieval query",
            "hyde_strategy": "one hypothetical reusable reasoning strategy description for this question type",
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def parse_response(text: str) -> dict[str, str]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"No JSON object in response: {text[:200]}")
    raw = json.loads(match.group(0))
    return {
        "query_rewrite": normalize_generated_text(str(raw.get("query_rewrite", ""))),
        "hyde_strategy": normalize_generated_text(str(raw.get("hyde_strategy", ""))),
    }


class JsonlCache:
    def __init__(self, path: str):
        self.path = path
        self.data = {}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        rec = json.loads(line)
                        self.data[rec["key"]] = rec

    def call(self, sample_id: str, question: str, dry_run: bool = False) -> tuple[dict[str, str], dict[str, Any], bool]:
        prompt = prompt_for_question(question)
        key = stable_hash({
            "version": METHOD_VERSION,
            "runtime": llm.runtime_config(),
            "system": SYSTEM,
            "prompt": prompt,
        })
        if key in self.data:
            rec = self.data[key]
            return rec["generated"], rec.get("runtime", {}), True
        if dry_run:
            raise RuntimeError(f"Missing query-method cache for {sample_id}")
        response = llm.call_once_with_metadata(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0,
            timeout=180,
        )
        generated = parse_response(response["text"])
        rec = {
            "key": key,
            "sample_id": sample_id,
            "prompt": prompt,
            "raw_response": response["text"],
            "generated": generated,
            "runtime": response.get("runtime", {}),
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.data[key] = rec
        return generated, rec["runtime"], False


def embed_strategies(strategies: list[dict[str, Any]]) -> np.ndarray:
    model = get_model()
    texts = [s["retrieval_text"] for s in strategies]
    return model.encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True)


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
        "answer_from_top3": c["answer_from_topk"] / n if n else 0.0,
        "scale_top3": c["scale_topk"] / n if n else 0.0,
    }


def evaluate_methods(
    sample: list[dict[str, Any]],
    generated_by_id: dict[str, dict[str, str]],
    strategies: list[dict[str, Any]],
    emb: np.ndarray,
    memory_by_schema: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    counters = {m: Counter() for m in METHODS}
    eligible_counters = {m: Counter() for m in METHODS}
    by_type = {m: defaultdict(Counter) for m in METHODS}
    records = []
    for rec in sample:
        absr = abstract_record(rec)
        eligible = gold_schema_in_memory(absr, memory_by_schema)
        generated = generated_by_id[rec["sample_id"]]
        query_texts = {
            "question_only": rec["question"],
            "query_rewrite": generated["query_rewrite"],
            "hyde": generated["hyde_strategy"],
        }
        method_records = {}
        for method, query_text in query_texts.items():
            hits = retrieve(query_text, strategies, emb, k=TOP_K)
            comp = compatibility(absr, hits)
            for k, v in comp.items():
                counters[method][k] += int(v)
                if eligible:
                    eligible_counters[method][k] += int(v)
            counters[method]["n"] += 1
            if eligible:
                eligible_counters[method]["n"] += 1
            by_type[method][absr["strategy_type"]]["n"] += 1
            by_type[method][absr["strategy_type"]]["eligible"] += int(eligible)
            for k, v in comp.items():
                by_type[method][absr["strategy_type"]][k] += int(v)
            method_records[method] = {"query_text": query_text, "compatibility": comp, "top_strategies": hits}
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
            "generated": generated,
            "methods": method_records,
        })
    return {
        method: {
            "overall": rates(counters[method]),
            "eligible_only": rates(eligible_counters[method]),
            "by_strategy_type": {
                t: rates(c) | {"eligible": int(c["eligible"])}
                for t, c in sorted(by_type[method].items())
            },
        }
        for method in METHODS
    } | {"records": records}


def examples(records: list[dict[str, Any]], best_method: str, limit: int = 5) -> dict[str, list[dict[str, Any]]]:
    success = []
    failure = []
    baseline_gain = []
    for rec in records:
        if not rec["gold"]["in_memory"]:
            continue
        best_comp = rec["methods"][best_method]["compatibility"]
        base_comp = rec["methods"]["question_only"]["compatibility"]
        item = {
            "sample_id": rec["sample_id"],
            "question": rec["question"],
            "gold_schema": rec["gold"]["schema_key"],
            "generated": rec["generated"],
            "best_top3": [h["schema_key"] for h in rec["methods"][best_method]["top_strategies"]],
            "question_top3": [h["schema_key"] for h in rec["methods"]["question_only"]["top_strategies"]],
        }
        if best_comp["schema_topk"] and len(success) < limit:
            success.append(item)
        if best_comp["schema_topk"] and not base_comp["schema_topk"] and len(baseline_gain) < limit:
            baseline_gain.append(item)
        if not best_comp["schema_topk"] and len(failure) < limit:
            failure.append(item)
        if len(success) >= limit and len(failure) >= limit and len(baseline_gain) >= limit:
            break
    return {"success": success, "failure": failure, "baseline_gain": baseline_gain}


def choose_recommendation(results: dict[str, Any]) -> str:
    eligible_schema = {m: results[m]["eligible_only"]["schema_top3"] for m in METHODS}
    overall_type = {m: results[m]["overall"]["type_top3"] for m in METHODS}
    # Exact schema is primary; type is tie-breaker for strategy retrieval usefulness.
    return sorted(METHODS, key=lambda m: (eligible_schema[m], overall_type[m]), reverse=True)[0]


def write_report(audit: dict[str, Any]) -> None:
    results = audit["results"]
    best = audit["recommended_method"]
    lines = [
        "# TAT-QA Query Retrieval Methods Audit",
        "",
        "Date: 2026-08-16",
        "",
        "Scope: Strategy retrieval query-method audit only. Frozen 30-item Strategy Memory, same 120-sample dev audit set, same embedding model, same top-3. No four-arm execution, no router, no strategy rewriting or family changes.",
        "",
        "## Setup",
        "",
        f"- Strategy memory: `data/tatqa/processed/tatqa_strategy_memory_v0.json` (30 frozen strategies).",
        f"- Fixed dev sample: {audit['sample_n']} examples, seed `{SEED}`.",
        f"- Gold schema present in frozen memory: {audit['eligible_n']} / {audit['sample_n']} ({audit['eligible_rate']:.3f}).",
        f"- Retriever: `{config.EMBED_MODEL}` on `{config.EMBED_DEVICE}`, top-{TOP_K}.",
        f"- Query-generation records required: {audit['sample_n']} (one DeepSeek call per sample when cache is cold; each call returns both rewrite and HyDE).",
        f"- Latest command API calls: {audit['api_calls_made']}; cache hits: {audit['cache_hits']}; cache records after run: {audit['cache_records_after']}.",
        "",
        "The rewrite/HyDE prompt used only the raw question text. It did not include gold answer, answer_type, scale, operator, derivation, or schema labels.",
        "",
        "## Overall Results",
        "",
        "| Method | Schema top1 | Schema top3 | Type top3 | Family top3 | Source top3 | Scale top3 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for method in METHODS:
        r = results[method]["overall"]
        lines.append(
            f"| `{method}` all | {r['schema_top1']:.3f} | {r['schema_top3']:.3f} | {r['type_top3']:.3f} | "
            f"{r['family_top3']:.3f} | {r['answer_from_top3']:.3f} | {r['scale_top3']:.3f} |"
        )
    lines.extend([
        "",
        "Eligible-only exact schema results:",
        "",
        "| Method | Schema top1 | Schema top3 | Type top3 | Family top3 |",
        "|---|---:|---:|---:|---:|",
    ])
    for method in METHODS:
        r = results[method]["eligible_only"]
        lines.append(f"| `{method}` | {r['schema_top1']:.3f} | {r['schema_top3']:.3f} | {r['type_top3']:.3f} | {r['family_top3']:.3f} |")
    lines.extend([
        "",
        "## By Strategy Type",
        "",
        "| Type | N | Method | Schema top3 | Type top3 | Family top3 |",
        "|---|---:|---|---:|---:|---:|",
    ])
    types = sorted(results["question_only"]["by_strategy_type"])
    for t in types:
        n = results["question_only"]["by_strategy_type"][t]["n"]
        for method in METHODS:
            r = results[method]["by_strategy_type"].get(t, {})
            lines.append(f"| `{t}` | {n} | `{method}` | {r.get('schema_top3', 0.0):.3f} | {r.get('type_top3', 0.0):.3f} | {r.get('family_top3', 0.0):.3f} |")
    ex = audit["examples"]
    lines.extend([
        "",
        "## Typical Successes",
        "",
    ])
    for item in ex["success"]:
        lines.append(f"- `{item['sample_id']}` gold `{item['gold_schema']}`; {best} top3 `{item['best_top3']}`; question: {item['question'][:180]}")
    lines.extend([
        "",
        "## Cases Improved Over Question-Only",
        "",
    ])
    for item in ex["baseline_gain"]:
        lines.append(f"- `{item['sample_id']}` gold `{item['gold_schema']}`; question-only `{item['question_top3']}` -> {best} `{item['best_top3']}`; rewrite: {item['generated']['query_rewrite'][:180]}")
    lines.extend([
        "",
        "## Typical Failures",
        "",
    ])
    for item in ex["failure"]:
        lines.append(f"- `{item['sample_id']}` gold `{item['gold_schema']}`; {best} top3 `{item['best_top3']}`; HyDE: {item['generated']['hyde_strategy'][:180]}")
    q = results["question_only"]["eligible_only"]["schema_top3"]
    rw = results["query_rewrite"]["eligible_only"]["schema_top3"]
    hy = results["hyde"]["eligible_only"]["schema_top3"]
    lines.extend([
        "",
        "## Interpretation",
        "",
        f"Exact schema top3 on eligible samples: question-only {q:.3f}, rewrite {rw:.3f}, HyDE {hy:.3f}.",
        f"Recommended method by exact schema top3 with type-top3 tie-break: `{best}`.",
        "",
        "Main failure modes:",
        "",
        "- Query-only methods still struggle to distinguish source/scale variants within the same broad family.",
        "- Rewriting can abstract away useful lexical cues needed to separate arithmetic from lookup questions.",
        "- HyDE often improves broad strategy type intent, but can hallucinate a generic strategy that misses exact schema source/scale.",
        "- Frozen v0 only covers top schema families, so some dev gold schemas remain impossible exact hits.",
        "",
        "## Decision",
        "",
        f"Decision: `FREEZE {best.upper()} STRATEGY RETRIEVAL FOR TAT-QA FOUR-ARM SMALL DRY-RUN`." if best != "question_only" else "Decision: `KEEP QUESTION-ONLY STRATEGY RETRIEVAL FOR TAT-QA FOUR-ARM SMALL DRY-RUN`.",
    ])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run(dry_run: bool = False) -> dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True)
    strategies = load_json(MEMORY_PATH)
    memory_by_schema = {s["schema_key"]: s for s in strategies}
    dev = parse_split("dev")
    sample = fixed_dev_sample(dev, AUDIT_N)
    cache = JsonlCache(CACHE_PATH)
    generated_by_id = {}
    api_calls = 0
    cache_hits = 0
    for rec in sample:
        generated, _, hit = cache.call(rec["sample_id"], rec["question"], dry_run=dry_run)
        generated_by_id[rec["sample_id"]] = generated
        cache_hits += int(hit)
        api_calls += int(not hit)
    emb = embed_strategies(strategies)
    results = evaluate_methods(sample, generated_by_id, strategies, emb, memory_by_schema)
    eligible_n = sum(1 for rec in sample if abstract_record(rec)["schema_key"] in memory_by_schema)
    recommended = choose_recommendation(results)
    audit = {
        "version": METHOD_VERSION,
        "sample_n": len(sample),
        "seed": SEED,
        "top_k": TOP_K,
        "strategy_count": len(strategies),
        "eligible_n": eligible_n,
        "eligible_rate": eligible_n / len(sample) if sample else 0.0,
        "api_calls_made": api_calls,
        "cache_hits": cache_hits,
        "cache_records_after": len(cache.data),
        "runtime_request": llm.runtime_config(),
        "prompt_contract": {
            "input": "question only",
            "forbidden": ["gold answer", "answer_type", "scale", "operator", "derivation", "schema labels"],
        },
        "results": results,
        "recommended_method": recommended,
        "examples": examples(results["records"], recommended),
    }
    dump_json(AUDIT_JSON_PATH, audit)
    write_report(audit)
    print(json.dumps({
        "sample_n": audit["sample_n"],
        "eligible_n": eligible_n,
        "api_calls_made": api_calls,
        "cache_hits": cache_hits,
        "question_schema_top3_eligible": results["question_only"]["eligible_only"]["schema_top3"],
        "rewrite_schema_top3_eligible": results["query_rewrite"]["eligible_only"]["schema_top3"],
        "hyde_schema_top3_eligible": results["hyde"]["eligible_only"]["schema_top3"],
        "recommended": recommended,
        "report": os.path.relpath(REPORT_PATH, ROOT),
    }, indent=2))
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Require all rewrite/HyDE outputs to be cached.")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
