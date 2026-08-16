"""TAT-QA four-arm small dry-run.

Runs one fixed 30-sample dev dry-run for None / Case / Strategy / Both.
The goal is pipeline validation and first memory-effect signal only; this
script does not tune prompts, retrieval, memory, or sample selection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from tatqa_case_memory import (  # noqa: E402
    CASE_MEMORY_PATH,
    make_retrieval_text,
    retrieve_cases,
)
from tatqa_evaluator import evaluate_contexts, raw_path  # noqa: E402
from tatqa_ingest import parse_split, render_text_context  # noqa: E402
from tatqa_query_retrieval_methods_audit import CACHE_PATH as HYDE_CACHE_PATH  # noqa: E402
from tatqa_strategy_retrieval_audit import (  # noqa: E402
    AUDIT_N as STRATEGY_AUDIT_N,
    MEMORY_PATH as STRATEGY_MEMORY_PATH,
    SEED,
    TOP_K as STRATEGY_TOP_K,
    fixed_dev_sample,
    load_json,
    retrieve as retrieve_strategies,
)

OUT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "tatqa")
REPORT_PATH = os.path.join(OUT_DIR, "TATQA_FOUR_ARM_DRY_RUN.md")
AUDIT_JSON_PATH = os.path.join(OUT_DIR, "tatqa_four_arm_dry_run.json")
EXEC_CACHE_PATH = os.path.join(OUT_DIR, "tatqa_four_arm_dry_run_cache.jsonl")

METHOD_VERSION = "tatqa_four_arm_dry_run_v1_fixed30_hyde_strategy"
SAMPLE_N = 30
CASE_TOP_K = 4
STRATEGY_TOP_K_FROZEN = STRATEGY_TOP_K
ARMS = ["none", "case", "strategy", "both"]
MAX_TOKENS = 900
TEMPERATURE = 0
CONCURRENCY = 4

SYSTEM = (
    "You answer TAT-QA financial table-and-text questions. Use the given context "
    "and optional memory only as reasoning support. Return only valid JSON with "
    'keys "answer" and "scale". Do not include explanations.'
)

ALLOWED_SCALES = {"", "thousand", "million", "billion", "percent"}


def dump_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def normalize_cell(value: Any) -> str:
    return " ".join(str(value).replace("\n", " ").split())


def render_table(table: list[list[Any]]) -> str:
    return "\n".join(
        f"row_{i}: " + " | ".join(normalize_cell(c) for c in row)
        for i, row in enumerate(table)
    )


def render_context(record: dict[str, Any]) -> str:
    return "\n".join([
        "Paragraphs:",
        render_text_context(record.get("paragraphs", [])),
        "",
        "Table:",
        render_table(record.get("table", [])),
    ]).strip()


def load_hyde_by_sample_id(path: str = HYDE_CACHE_PATH) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            out[rec["sample_id"]] = rec["generated"]
    return out


def load_strategy_embeddings(strategies: list[dict[str, Any]]) -> np.ndarray:
    model = get_model()
    texts = [s["retrieval_text"] for s in strategies]
    return model.encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True)


def short_case(case: dict[str, Any], score: float) -> str:
    paras = " ".join(normalize_cell(p.get("text", "")) for p in case.get("relevant_paragraphs", [])[:2])
    if len(paras) > 420:
        paras = paras[:420].rstrip() + "..."
    table_preview = render_table(case.get("table", [])[:6])
    return "\n".join([
        f"Case {case['case_id']} score={score:.3f}",
        f"Question: {case.get('question', '')}",
        f"Answer type/source/scale: {case.get('answer_type')} / {case.get('answer_from')} / {case.get('scale') or 'none'}",
        f"Answer: {case.get('answer')}",
        f"Derivation: {case.get('derivation') or '(none)'}",
        f"Relevant paragraphs: {paras or '(none)'}",
        f"Table preview:\n{table_preview}",
    ])


def short_strategy(strategy: dict[str, Any], score: float) -> str:
    return "\n".join([
        f"Strategy {strategy['strategy_id']} score={score:.3f}",
        f"Type/family/source/scale: {strategy['strategy_type']} / {strategy['family']} / {strategy['answer_from']} / {strategy['scale']}",
        f"Description: {strategy.get('description', '')}",
        "Evidence guidance: " + " ; ".join(strategy.get("evidence_guidance", [])[:3]),
        "Operand roles: " + " ; ".join(strategy.get("operand_roles", [])[:4]),
        f"Answer form: {strategy.get('answer_form', '')}",
        "Scale notes: " + " ; ".join(strategy.get("scale_notes", [])[:3]),
        "Risk notes: " + " ; ".join(strategy.get("risk_notes", [])[:3]),
    ])


def memory_block(case_blocks: list[str], strategy_blocks: list[str], arm: str) -> str:
    chunks = []
    if arm in {"case", "both"} and case_blocks:
        chunks.append(
            "SIMILAR SOLVED CASES\n"
            "Use these only for analogous evidence locating, answer format, scale handling, and reasoning structure. "
            "Do not copy their numbers or answers unless they are present in the current context.\n"
            + "\n\n".join(case_blocks)
        )
    if arm in {"strategy", "both"} and strategy_blocks:
        chunks.append(
            "RETRIEVED REASONING STRATEGIES\n"
            "Use the applicable strategy if it matches the current question. Ignore conflicting or irrelevant strategies.\n"
            + "\n\n".join(strategy_blocks)
        )
    return "\n\n".join(chunks)


def build_prompt(record: dict[str, Any], arm: str, case_blocks: list[str], strategy_blocks: list[str]) -> str:
    payload = {
        "task": "Answer the TAT-QA question using the context. If a memory block is present, use it only as support.",
        "question": record["question"],
        "context": render_context(record),
        "memory": memory_block(case_blocks, strategy_blocks, arm),
        "output_contract": {
            "answer": "string, number, or list of strings for multi-span answers",
            "scale": "one of '', 'thousand', 'million', 'billion', 'percent'",
        },
        "scale_rules": [
            "Use an empty string when no explicit output scale is needed.",
            "Use percent only for percentage answers.",
            "If the answer is a table/text span such as '$1,496.5' and the question asks for the value as reported, preserve the span and choose the scale implied by the table/context.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def parse_answer(text: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None, "no_json_object"
        raw = json.loads(match.group(0))
        answer = raw.get("answer")
        scale = raw.get("scale", "")
        if scale is None:
            scale = ""
        scale = str(scale).strip().lower()
        if scale in {"none", "no scale", "n/a", "na"}:
            scale = ""
        if scale not in ALLOWED_SCALES:
            return {"answer": answer, "scale": scale}, f"invalid_scale:{scale}"
        return {"answer": answer, "scale": scale}, None
    except Exception as exc:  # noqa: BLE001
        return None, f"parse_exception:{type(exc).__name__}"


class ExecCache:
    def __init__(self, path: str):
        self.path = path
        self.data: dict[str, dict[str, Any]] = {}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        rec = json.loads(line)
                        self.data[rec["key"]] = rec

    def call(self, key: str, sample_id: str, arm: str, messages: list[dict[str, str]], dry_run: bool) -> tuple[dict[str, Any], bool]:
        if key in self.data:
            return self.data[key], True
        if dry_run:
            raise RuntimeError(f"Missing execution cache for {sample_id}/{arm}")
        response = llm.call_once_with_metadata(messages, max_tokens=MAX_TOKENS, temperature=TEMPERATURE, timeout=240)
        parsed, parse_error = parse_answer(response["text"])
        rec = {
            "key": key,
            "sample_id": sample_id,
            "arm": arm,
            "raw_response": response["text"],
            "parsed": parsed,
            "parse_error": parse_error,
            "runtime": response.get("runtime", {}),
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.data[key] = rec
        return rec, False


def select_sample() -> list[dict[str, Any]]:
    # Freeze as the first 30 examples from the already-audited 120-sample dev set.
    dev = parse_split("dev")
    return fixed_dev_sample(dev, STRATEGY_AUDIT_N)[:SAMPLE_N]


def prepare_retrieval(sample: list[dict[str, Any]]) -> dict[str, Any]:
    cases = load_json(CASE_MEMORY_PATH)
    cases_by_id = {case["case_id"]: case for case in cases}
    strategies = load_json(STRATEGY_MEMORY_PATH)
    strategy_by_id = {s["strategy_id"]: s for s in strategies}
    strategy_emb = load_strategy_embeddings(strategies)
    hyde_by_id = load_hyde_by_sample_id()
    prep = {}
    missing_hyde = [r["sample_id"] for r in sample if r["sample_id"] not in hyde_by_id]
    if missing_hyde:
        raise RuntimeError(f"Missing frozen HyDE cache for {len(missing_hyde)} samples: {missing_hyde[:5]}")
    for rec in sample:
        case_query = make_retrieval_text(rec, memory_side=False)
        case_hits = retrieve_cases(case_query, k=CASE_TOP_K, exclude_source_id=rec["source_id"])
        case_blocks = [short_case(cases_by_id[h["case_id"]], h["score"]) for h in case_hits]
        hyde_query = hyde_by_id[rec["sample_id"]]["hyde_strategy"]
        strategy_hits = retrieve_strategies(hyde_query, strategies, strategy_emb, k=STRATEGY_TOP_K_FROZEN)
        strategy_blocks = [short_strategy(strategy_by_id[h["strategy_id"]], h["score"]) for h in strategy_hits]
        prep[rec["sample_id"]] = {
            "case_hits": case_hits,
            "strategy_hits": strategy_hits,
            "hyde_query": hyde_query,
            "case_blocks": case_blocks,
            "strategy_blocks": strategy_blocks,
        }
    return prep


def cache_key(sample_index: int, record: dict[str, Any], arm: str, prompt: str, retrieval: dict[str, Any]) -> str:
    return stable_hash({
        "version": METHOD_VERSION,
        "sample_index": sample_index,
        "sample_id": record["sample_id"],
        "arm": arm,
        "runtime": llm.runtime_config(),
        "requested_model": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "thinking_mode": False,
        "case_top_k": CASE_TOP_K,
        "strategy_top_k": STRATEGY_TOP_K_FROZEN,
        "case_ids": [h["case_id"] for h in retrieval["case_hits"]],
        "strategy_ids": [h["strategy_id"] for h in retrieval["strategy_hits"]],
        "strategy_query_method": "frozen_hyde",
        "system": SYSTEM,
        "prompt": prompt,
    })


def subset_gold_contexts(sample: list[dict[str, Any]]) -> list[dict[str, Any]]:
    wanted = {rec["native_question_uid"] for rec in sample}
    raw = load_json(raw_path("dev"))
    out = []
    for ctx in raw:
        qs = [q for q in ctx.get("questions", []) if q.get("uid") in wanted]
        if qs:
            c = dict(ctx)
            c["questions"] = qs
            out.append(c)
    return out


def evaluate_arm(gold_contexts: list[dict[str, Any]], arm_outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    predictions = {}
    parse_failures = 0
    invalid_scale = 0
    for uid, out in arm_outputs.items():
        parsed = out.get("parsed")
        if parsed is None:
            parse_failures += 1
            predictions[uid] = [None, ""]
            continue
        if out.get("parse_error"):
            invalid_scale += int(str(out["parse_error"]).startswith("invalid_scale"))
        predictions[uid] = [parsed.get("answer"), parsed.get("scale", "")]
    result = evaluate_contexts(gold_contexts, predictions)
    result.pop("details", None)
    result["parse_failures"] = parse_failures
    result["invalid_scale_parse_errors"] = invalid_scale
    return result


def observed_runtime_summary(outputs: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    models = Counter()
    fingerprints = Counter()
    backends = Counter()
    endpoints = Counter()
    for arm_outputs in outputs.values():
        for out in arm_outputs.values():
            rt = out.get("runtime", {})
            models[rt.get("response_model") or rt.get("effective_model") or "missing"] += 1
            fingerprints[rt.get("system_fingerprint") or rt.get("model_version") or "missing"] += 1
            backends[rt.get("backend") or "missing"] += 1
            endpoints[rt.get("endpoint") or rt.get("base_url") or "missing"] += 1
    return {
        "response_models": dict(models),
        "system_fingerprints": dict(fingerprints),
        "backends": dict(backends),
        "endpoints": dict(endpoints),
    }


def run(dry_run: bool = False) -> dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True)
    sample = select_sample()
    retrieval = prepare_retrieval(sample)
    cache = ExecCache(EXEC_CACHE_PATH)
    outputs: dict[str, dict[str, dict[str, Any]]] = {arm: {} for arm in ARMS}
    tasks = []
    for idx, rec in enumerate(sample):
        r = retrieval[rec["sample_id"]]
        for arm in ARMS:
            prompt = build_prompt(rec, arm, r["case_blocks"], r["strategy_blocks"])
            key = cache_key(idx, rec, arm, prompt, r)
            messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
            tasks.append((key, rec["sample_id"], rec["native_question_uid"], arm, messages))

    api_calls = 0
    cache_hits = 0
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futs = {
            ex.submit(cache.call, key, sample_id, arm, messages, dry_run): (uid, arm)
            for key, sample_id, uid, arm, messages in tasks
        }
        for fut in as_completed(futs):
            uid, arm = futs[fut]
            rec, hit = fut.result()
            outputs[arm][uid] = rec
            cache_hits += int(hit)
            api_calls += int(not hit)

    gold_contexts = subset_gold_contexts(sample)
    evals = {arm: evaluate_arm(gold_contexts, outputs[arm]) for arm in ARMS}
    details_by_arm = {}
    for arm in ARMS:
        predictions = {
            uid: [out["parsed"].get("answer") if out.get("parsed") else None, out["parsed"].get("scale", "") if out.get("parsed") else ""]
            for uid, out in outputs[arm].items()
        }
        detailed = evaluate_contexts(gold_contexts, predictions)
        details_by_arm[arm] = {d["uid"]: d for d in detailed["details"]}

    correctness = {}
    for rec in sample:
        uid = rec["native_question_uid"]
        correctness[rec["sample_id"]] = {
            arm: {
                "em": float(details_by_arm[arm][uid]["em"]),
                "f1": float(details_by_arm[arm][uid]["f1"]),
            }
            for arm in ARMS
        }

    oracle_em = float(np.mean([max(correctness[r["sample_id"]][a]["em"] for a in ARMS) for r in sample]))
    best_fixed = max(ARMS, key=lambda a: evals[a]["exact_match"])
    arm_correct = {
        arm: {r["sample_id"] for r in sample if correctness[r["sample_id"]][arm]["em"] == 1.0}
        for arm in ARMS
    }
    event_counts = {
        "case_only": len(arm_correct["case"] - arm_correct["none"] - arm_correct["strategy"] - arm_correct["both"]),
        "strategy_only": len(arm_correct["strategy"] - arm_correct["none"] - arm_correct["case"] - arm_correct["both"]),
        "none_only": len(arm_correct["none"] - arm_correct["case"] - arm_correct["strategy"] - arm_correct["both"]),
        "both_only": len(arm_correct["both"] - arm_correct["none"] - arm_correct["case"] - arm_correct["strategy"]),
        "none_gt_both": sum(correctness[r["sample_id"]]["none"]["em"] > correctness[r["sample_id"]]["both"]["em"] for r in sample),
        "case_gt_both": sum(correctness[r["sample_id"]]["case"]["em"] > correctness[r["sample_id"]]["both"]["em"] for r in sample),
        "strategy_gt_both": sum(correctness[r["sample_id"]]["strategy"]["em"] > correctness[r["sample_id"]]["both"]["em"] for r in sample),
    }
    by_answer_type = {}
    for arm in ARMS:
        by_answer_type[arm] = evals[arm]["by_answer_type"]

    records = []
    for rec in sample:
        sid = rec["sample_id"]
        records.append({
            "sample_id": sid,
            "uid": rec["native_question_uid"],
            "question": rec["question"],
            "answer_type": rec["answer_type"],
            "answer_from": rec["answer_from"],
            "scale": rec["scale"],
            "gold_answer": rec["answer"],
            "retrieval": {
                "case_hits": retrieval[sid]["case_hits"],
                "strategy_hits": retrieval[sid]["strategy_hits"],
                "hyde_query": retrieval[sid]["hyde_query"],
            },
            "outputs": {
                arm: {
                    "parsed": outputs[arm][rec["native_question_uid"]].get("parsed"),
                    "parse_error": outputs[arm][rec["native_question_uid"]].get("parse_error"),
                    "raw_response": outputs[arm][rec["native_question_uid"]].get("raw_response"),
                    "em": correctness[sid][arm]["em"],
                    "f1": correctness[sid][arm]["f1"],
                }
                for arm in ARMS
            },
            "correct_arms_em": [arm for arm in ARMS if correctness[sid][arm]["em"] == 1.0],
        })

    audit = {
        "version": METHOD_VERSION,
        "sample_n": len(sample),
        "sample_selection": f"first {SAMPLE_N} of fixed {STRATEGY_AUDIT_N}-sample strategy audit dev set, seed {SEED}",
        "arms": ARMS,
        "case_top_k": CASE_TOP_K,
        "strategy_top_k": STRATEGY_TOP_K_FROZEN,
        "strategy_query_method": "frozen_hyde",
        "runtime_request": llm.runtime_config(),
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "observed_runtime": observed_runtime_summary(outputs),
        "api_calls_made": api_calls,
        "cache_hits": cache_hits,
        "cache_records_after": len(cache.data),
        "arm_metrics": evals,
        "best_fixed_arm": best_fixed,
        "best_fixed_em": evals[best_fixed]["exact_match"],
        "sample_oracle_em": oracle_em,
        "event_counts": event_counts,
        "by_answer_type": by_answer_type,
        "records": records,
        "decision": "PROCEED" if max(evals[a]["exact_match"] for a in ARMS) > 0 and sum(evals[a]["parse_failures"] for a in ARMS) <= 3 else "FIX PIPELINE FIRST",
    }
    dump_json(AUDIT_JSON_PATH, audit)
    write_report(audit)
    print(json.dumps({
        "sample_n": audit["sample_n"],
        "api_calls_made": api_calls,
        "cache_hits": cache_hits,
        "arm_em": {a: evals[a]["exact_match"] for a in ARMS},
        "arm_f1": {a: evals[a]["f1"] for a in ARMS},
        "best_fixed_arm": best_fixed,
        "best_fixed_em": audit["best_fixed_em"],
        "sample_oracle_em": oracle_em,
        "decision": audit["decision"],
        "report": os.path.relpath(REPORT_PATH, ROOT),
    }, indent=2))
    return audit


def fmt(v: float) -> str:
    return f"{v:.3f}"


def write_report(audit: dict[str, Any]) -> None:
    lines = [
        "# TAT-QA Four-Arm Small Dry-Run",
        "",
        "Date: 2026-08-16",
        "",
        "Scope: one fixed 30-sample TAT-QA dev dry-run for pipeline validation. No prompt/retrieval/memory tuning, no router, no sample adjustment.",
        "",
        "## Setup",
        "",
        f"- Sample: {audit['sample_selection']}.",
        f"- Arms: {', '.join(audit['arms'])}.",
        f"- Case retrieval: existing TAT-QA train Case Memory, top-{audit['case_top_k']}, source_id exclusion.",
        f"- Strategy retrieval: frozen HyDE query + frozen 30-item Strategy Memory, top-{audit['strategy_top_k']}.",
        f"- Runtime request: `{audit['runtime_request']}`; temperature={audit['temperature']}; max_tokens={audit['max_tokens']}; thinking disabled by client.",
        f"- Observed response models: `{audit['observed_runtime']['response_models']}`; fingerprints: `{audit['observed_runtime']['system_fingerprints']}`.",
        f"- Execution cache records after run: {audit['cache_records_after']}; latest command API calls={audit['api_calls_made']}; cache hits={audit['cache_hits']}. A cold run requires one execution call per sample-arm pair ({audit['sample_n']} x {len(audit['arms'])} = {audit['sample_n'] * len(audit['arms'])}).",
        "- Evaluator: project wrapper over official TAT-QA `TaTQAEmAndF1`.",
        "",
        "## Four-Arm Metrics",
        "",
        "| Arm | EM | F1 | Scale score | Parse failures | Invalid-scale parse errors |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for arm in ARMS:
        r = audit["arm_metrics"][arm]
        lines.append(
            f"| `{arm}` | {fmt(r['exact_match'])} | {fmt(r['f1'])} | {fmt(r['scale_score'])} | "
            f"{r['parse_failures']} | {r['invalid_scale_parse_errors']} |"
        )
    lines.extend([
        "",
        f"Best Fixed: `{audit['best_fixed_arm']}` EM={fmt(audit['best_fixed_em'])}.",
        f"Sample Oracle EM={fmt(audit['sample_oracle_em'])}.",
        "",
        "## Memory Effect Events",
        "",
    ])
    for k, v in audit["event_counts"].items():
        lines.append(f"- `{k}`: {v}")
    lines.extend([
        "",
        "## By Answer Type",
        "",
        "| Answer type | Arm | N | EM | F1 |",
        "|---|---|---:|---:|---:|",
    ])
    answer_types = sorted({t for arm in ARMS for t in audit["by_answer_type"][arm]})
    for answer_type in answer_types:
        for arm in ARMS:
            r = audit["by_answer_type"][arm].get(answer_type, {"count": 0, "em": 0.0, "f1": 0.0})
            lines.append(f"| `{answer_type}` | `{arm}` | {r['count']} | {fmt(r['em'])} | {fmt(r['f1'])} |")
    lines.extend([
        "",
        "## Typical Samples",
        "",
    ])
    interesting = [
        rec for rec in audit["records"]
        if len(set(rec["correct_arms_em"])) not in {0, 4}
    ][:8]
    if not interesting:
        interesting = audit["records"][:5]
    for rec in interesting:
        parsed = {arm: rec["outputs"][arm]["parsed"] for arm in ARMS}
        lines.append(
            f"- `{rec['sample_id']}` type={rec['answer_type']} scale={rec['scale'] or 'none'} "
            f"correct={rec['correct_arms_em']} question={rec['question'][:160]} predictions={parsed}"
        )
    lines.extend([
        "",
        "## Pipeline Notes",
        "",
        "- Model outputs were parsed as JSON `answer` + `scale` before official evaluation.",
        "- Strategy HyDE retrieval reused the frozen cached query-generation artifact; no strategy content or family was modified.",
        "- Gold answer/type/scale/derivation were used only for evaluation and post-hoc reporting.",
        "",
        "## Decision",
        "",
        f"Decision: `{audit['decision']}`.",
    ])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Require all execution outputs to be cached.")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
