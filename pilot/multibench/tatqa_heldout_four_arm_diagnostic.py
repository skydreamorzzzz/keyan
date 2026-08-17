"""TAT-QA fresh held-out four-arm diagnostic.

Runs one fixed 120-sample dev subset disjoint from the prior Strategy retrieval
audit sample. Protocol is frozen: None / Case / Strategy / Both, Case top-4,
HyDE Strategy top-3, existing prompt/runtime, and canonicalized TAT-QA
evaluation. No prompt, retrieval, memory, or sample tuning.
"""
from __future__ import annotations

import argparse
import json
import os
import random
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

import llm  # noqa: E402
from tatqa_case_memory import CASE_MEMORY_PATH, make_retrieval_text, retrieve_cases  # noqa: E402
from tatqa_evaluator import evaluate_contexts, raw_path  # noqa: E402
from tatqa_four_arm_dry_run import (  # noqa: E402
    ARMS,
    CASE_TOP_K,
    CONCURRENCY,
    MAX_TOKENS,
    STRATEGY_TOP_K_FROZEN,
    SYSTEM,
    TEMPERATURE,
    ExecCache,
    build_prompt,
    cache_key as dry_run_cache_key,
    dump_json,
    load_json,
    observed_runtime_summary,
    parse_answer,
    short_case,
    short_strategy,
    stable_hash,
)
from tatqa_ingest import parse_split  # noqa: E402
from tatqa_output_normalization_audit import canonicalize_prediction  # noqa: E402
from tatqa_query_retrieval_methods_audit import JsonlCache as HyDECache  # noqa: E402
from tatqa_strategy_retrieval_audit import (  # noqa: E402
    AUDIT_N as PREVIOUS_AUDIT_N,
    MEMORY_PATH as STRATEGY_MEMORY_PATH,
    SEED as PREVIOUS_AUDIT_SEED,
    fixed_dev_sample,
    retrieve as retrieve_strategies,
)

OUT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "tatqa")
REPORT_PATH = os.path.join(OUT_DIR, "TATQA_HELDOUT_FOUR_ARM_DIAGNOSTIC.md")
AUDIT_JSON_PATH = os.path.join(OUT_DIR, "tatqa_heldout_four_arm_diagnostic.json")
EXEC_CACHE_PATH = os.path.join(OUT_DIR, "tatqa_heldout_four_arm_diagnostic_cache.jsonl")

METHOD_VERSION = "tatqa_heldout_four_arm_diagnostic_v1_disjoint120"
HELDOUT_N = 120
HELDOUT_SEED = 20260817


def select_heldout_sample() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    dev = parse_split("dev")
    previous = fixed_dev_sample(dev, PREVIOUS_AUDIT_N)
    previous_ids = {rec["sample_id"] for rec in previous}
    candidates = [rec for rec in dev if rec["sample_id"] not in previous_ids]
    rng = random.Random(HELDOUT_SEED)
    sample = rng.sample(candidates, HELDOUT_N)
    assert not any(rec["sample_id"] in previous_ids for rec in sample)
    return sample, {
        "heldout_n": HELDOUT_N,
        "heldout_seed": HELDOUT_SEED,
        "previous_exclusion_n": len(previous_ids),
        "previous_seed": PREVIOUS_AUDIT_SEED,
        "previous_n": PREVIOUS_AUDIT_N,
        "dev_n": len(dev),
        "candidate_n_after_exclusion": len(candidates),
    }


def load_strategy_embeddings(strategies: list[dict[str, Any]]) -> np.ndarray:
    from retrieval import get_model  # local import keeps test import cheap

    model = get_model()
    texts = [s["retrieval_text"] for s in strategies]
    return model.encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True)


def prepare_retrieval(sample: list[dict[str, Any]], dry_run: bool) -> tuple[dict[str, Any], dict[str, int]]:
    cases = load_json(CASE_MEMORY_PATH)
    cases_by_id = {case["case_id"]: case for case in cases}
    strategies = load_json(STRATEGY_MEMORY_PATH)
    strategy_by_id = {s["strategy_id"]: s for s in strategies}
    strategy_emb = load_strategy_embeddings(strategies)
    hyde_cache = HyDECache(os.path.join(OUT_DIR, "tatqa_query_retrieval_methods_cache.jsonl"))
    prep = {}
    hyde_calls = 0
    hyde_hits = 0
    for rec in sample:
        generated, _, hit = hyde_cache.call(rec["sample_id"], rec["question"], dry_run=dry_run)
        hyde_calls += int(not hit)
        hyde_hits += int(hit)
        case_query = make_retrieval_text(rec, memory_side=False)
        case_hits = retrieve_cases(case_query, k=CASE_TOP_K, exclude_source_id=rec["source_id"])
        case_blocks = [short_case(cases_by_id[h["case_id"]], h["score"]) for h in case_hits]
        strategy_hits = retrieve_strategies(generated["hyde_strategy"], strategies, strategy_emb, k=STRATEGY_TOP_K_FROZEN)
        strategy_blocks = [short_strategy(strategy_by_id[h["strategy_id"]], h["score"]) for h in strategy_hits]
        prep[rec["sample_id"]] = {
            "hyde_query": generated["hyde_strategy"],
            "case_hits": case_hits,
            "strategy_hits": strategy_hits,
            "case_blocks": case_blocks,
            "strategy_blocks": strategy_blocks,
        }
    return prep, {"hyde_api_calls": hyde_calls, "hyde_cache_hits": hyde_hits, "hyde_cache_records_after": len(hyde_cache.data)}


def heldout_cache_key(sample_index: int, record: dict[str, Any], arm: str, prompt: str, retrieval: dict[str, Any]) -> str:
    payload = {
        "version": METHOD_VERSION,
        "sample_index": sample_index,
        "sample_id": record["sample_id"],
        "arm": arm,
        "runtime": llm.runtime_config(),
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "thinking_mode": False,
        "case_top_k": CASE_TOP_K,
        "strategy_top_k": STRATEGY_TOP_K_FROZEN,
        "strategy_query_method": "frozen_hyde",
        "case_ids": [h["case_id"] for h in retrieval["case_hits"]],
        "strategy_ids": [h["strategy_id"] for h in retrieval["strategy_hits"]],
        "system": SYSTEM,
        "prompt": prompt,
    }
    return stable_hash(payload)


def subset_gold_contexts(uids: set[str]) -> list[dict[str, Any]]:
    raw = load_json(raw_path("dev"))
    out = []
    for ctx in raw:
        qs = [q for q in ctx.get("questions", []) if q.get("uid") in uids]
        if qs:
            c = dict(ctx)
            c["questions"] = qs
            out.append(c)
    return out


def predictions_for_arm(outputs: dict[str, dict[str, Any]], canonicalized: bool) -> tuple[dict[str, Any], dict[str, list[str]], int]:
    predictions = {}
    changes = {}
    normalization_failures = 0
    for uid, out in outputs.items():
        parsed = out.get("parsed")
        if canonicalized:
            try:
                parsed, tags = canonicalize_prediction(parsed)
            except Exception:  # noqa: BLE001
                tags = ["normalization_exception"]
                normalization_failures += 1
            changes[uid] = tags
        if parsed is None:
            predictions[uid] = [None, ""]
        else:
            predictions[uid] = [parsed.get("answer"), parsed.get("scale", "")]
    return predictions, changes, normalization_failures


def evaluate_outputs(gold_contexts: list[dict[str, Any]], outputs: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    arm_metrics = {}
    details_by_arm = {}
    normalization_changes = {}
    normalization_failures = {}
    for arm in ARMS:
        predictions, changes, failures = predictions_for_arm(outputs[arm], canonicalized=True)
        result = evaluate_contexts(gold_contexts, predictions)
        details_by_arm[arm] = {d["uid"]: d for d in result["details"]}
        result_no_details = dict(result)
        result_no_details.pop("details", None)
        parse_failures = sum(1 for out in outputs[arm].values() if out.get("parsed") is None)
        invalid_scale = sum(1 for out in outputs[arm].values() if str(out.get("parse_error") or "").startswith("invalid_scale"))
        result_no_details["parse_failures"] = parse_failures
        result_no_details["invalid_scale_parse_errors"] = invalid_scale
        result_no_details["normalization_failures"] = failures
        arm_metrics[arm] = result_no_details
        normalization_changes[arm] = changes
        normalization_failures[arm] = failures
    return {
        "arm_metrics": arm_metrics,
        "details_by_arm": details_by_arm,
        "normalization_changes": normalization_changes,
        "normalization_failures": normalization_failures,
    }


def event_counts(records: list[dict[str, Any]], details_by_arm: dict[str, dict[str, dict[str, Any]]]) -> dict[str, int]:
    def uid(rec: dict[str, Any]) -> str:
        return rec.get("uid") or rec["native_question_uid"]

    arm_correct = {
        arm: {rec["sample_id"] for rec in records if float(details_by_arm[arm][uid(rec)]["em"]) == 1.0}
        for arm in ARMS
    }
    return {
        "case_only": len(arm_correct["case"] - arm_correct["none"] - arm_correct["strategy"] - arm_correct["both"]),
        "strategy_only": len(arm_correct["strategy"] - arm_correct["none"] - arm_correct["case"] - arm_correct["both"]),
        "both_only": len(arm_correct["both"] - arm_correct["none"] - arm_correct["case"] - arm_correct["strategy"]),
        "none_only": len(arm_correct["none"] - arm_correct["case"] - arm_correct["strategy"] - arm_correct["both"]),
        "none_gt_both": sum(float(details_by_arm["none"][uid(rec)]["em"]) > float(details_by_arm["both"][uid(rec)]["em"]) for rec in records),
        "case_gt_both": sum(float(details_by_arm["case"][uid(rec)]["em"]) > float(details_by_arm["both"][uid(rec)]["em"]) for rec in records),
        "strategy_gt_both": sum(float(details_by_arm["strategy"][uid(rec)]["em"]) > float(details_by_arm["both"][uid(rec)]["em"]) for rec in records),
    }


def run(dry_run: bool = False) -> dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True)
    sample, sample_info = select_heldout_sample()
    retrieval, hyde_stats = prepare_retrieval(sample, dry_run=dry_run)
    cache = ExecCache(EXEC_CACHE_PATH)
    outputs: dict[str, dict[str, dict[str, Any]]] = {arm: {} for arm in ARMS}
    tasks = []
    for idx, rec in enumerate(sample):
        prep = retrieval[rec["sample_id"]]
        for arm in ARMS:
            prompt = build_prompt(rec, arm, prep["case_blocks"], prep["strategy_blocks"])
            key = heldout_cache_key(idx, rec, arm, prompt, prep)
            messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
            tasks.append((key, rec["sample_id"], rec["native_question_uid"], arm, messages))

    execution_calls = 0
    execution_hits = 0
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futs = {
            ex.submit(cache.call, key, sample_id, arm, messages, dry_run): (uid, arm)
            for key, sample_id, uid, arm, messages in tasks
        }
        for fut in as_completed(futs):
            uid, arm = futs[fut]
            rec, hit = fut.result()
            outputs[arm][uid] = rec
            execution_calls += int(not hit)
            execution_hits += int(hit)

    gold_contexts = subset_gold_contexts({rec["native_question_uid"] for rec in sample})
    evaluated = evaluate_outputs(gold_contexts, outputs)
    arm_metrics = evaluated["arm_metrics"]
    details_by_arm = evaluated["details_by_arm"]
    events = event_counts(sample, details_by_arm)
    best_fixed_arm = max(ARMS, key=lambda arm: arm_metrics[arm]["exact_match"])
    best_fixed_em = arm_metrics[best_fixed_arm]["exact_match"]
    oracle_em = float(np.mean([max(float(details_by_arm[arm][rec["native_question_uid"]]["em"]) for arm in ARMS) for rec in sample]))
    oracle_gap = oracle_em - best_fixed_em

    records = []
    for rec in sample:
        sid = rec["sample_id"]
        uid = rec["native_question_uid"]
        records.append({
            "sample_id": sid,
            "uid": uid,
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
                    "parsed": outputs[arm][uid].get("parsed"),
                    "parse_error": outputs[arm][uid].get("parse_error"),
                    "normalization_changes": evaluated["normalization_changes"][arm].get(uid, []),
                    "raw_response": outputs[arm][uid].get("raw_response"),
                    "em": float(details_by_arm[arm][uid]["em"]),
                    "f1": float(details_by_arm[arm][uid]["f1"]),
                }
                for arm in ARMS
            },
            "correct_arms_em": [arm for arm in ARMS if float(details_by_arm[arm][uid]["em"]) == 1.0],
        })

    norm_change_count = sum(
        1 for arm in ARMS for tags in evaluated["normalization_changes"][arm].values() if tags
    )
    audit = {
        "version": METHOD_VERSION,
        "sample_info": sample_info,
        "sample_n": len(sample),
        "arms": ARMS,
        "case_top_k": CASE_TOP_K,
        "strategy_top_k": STRATEGY_TOP_K_FROZEN,
        "strategy_query_method": "frozen_hyde",
        "evaluation_contract": "canonicalized TAT-QA prediction contract from TATQA_OUTPUT_NORMALIZATION_AUDIT.md",
        "runtime_request": llm.runtime_config(),
        "observed_runtime": observed_runtime_summary(outputs),
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "hyde_stats": hyde_stats,
        "execution_api_calls": execution_calls,
        "execution_cache_hits": execution_hits,
        "execution_cache_records_after": len(cache.data),
        "cold_run_call_budget": {
            "hyde_generation_max_calls": len(sample),
            "execution_calls": len(sample) * len(ARMS),
            "note": "Latest dry-run counters may be zero after cache replay; cold execution filled this namespace once.",
        },
        "normalization_changed_predictions": norm_change_count,
        "arm_metrics": arm_metrics,
        "by_answer_type": {arm: arm_metrics[arm]["by_answer_type"] for arm in ARMS},
        "best_fixed_arm": best_fixed_arm,
        "best_fixed_em": best_fixed_em,
        "sample_oracle_em": oracle_em,
        "oracle_gap": oracle_gap,
        "event_counts": events,
        "records": records,
        "decision": "PROCEED TO REPEATED RUNS" if oracle_gap >= 0.02 and max(events["case_gt_both"], events["strategy_gt_both"], events["none_gt_both"]) >= 3 else "TAT-QA MEMORY SIGNAL TOO WEAK",
    }
    dump_json(AUDIT_JSON_PATH, audit)
    write_report(audit)
    print(json.dumps({
        "sample_n": audit["sample_n"],
        "hyde_api_calls": hyde_stats["hyde_api_calls"],
        "execution_api_calls": execution_calls,
        "arm_em": {arm: arm_metrics[arm]["exact_match"] for arm in ARMS},
        "arm_f1": {arm: arm_metrics[arm]["f1"] for arm in ARMS},
        "best_fixed_arm": best_fixed_arm,
        "best_fixed_em": best_fixed_em,
        "sample_oracle_em": oracle_em,
        "oracle_gap": oracle_gap,
        "events": events,
        "decision": audit["decision"],
        "report": os.path.relpath(REPORT_PATH, ROOT),
    }, indent=2))
    return audit


def fmt(value: float) -> str:
    return f"{value:.3f}"


def write_report(audit: dict[str, Any]) -> None:
    lines = [
        "# TAT-QA Held-Out Four-Arm Diagnostic",
        "",
        "Date: 2026-08-17",
        "",
        "Scope: fresh held-out TAT-QA dev diagnostic. One run per sample-arm. No prompt/retrieval/memory/sample tuning.",
        "",
        "## Setup",
        "",
        f"- Sample: {audit['sample_n']} dev samples drawn with seed `{audit['sample_info']['heldout_seed']}` from dev after excluding the prior Strategy retrieval audit set ({audit['sample_info']['previous_exclusion_n']} samples, seed `{audit['sample_info']['previous_seed']}`).",
        f"- Candidate pool after exclusion: {audit['sample_info']['candidate_n_after_exclusion']} / {audit['sample_info']['dev_n']}.",
        f"- Arms: {', '.join(audit['arms'])}.",
        f"- Case retrieval: top-{audit['case_top_k']} existing TAT-QA train Case Memory with source_id exclusion.",
        f"- Strategy retrieval: frozen HyDE + top-{audit['strategy_top_k']} frozen Strategy Memory.",
        f"- Evaluation: {audit['evaluation_contract']}.",
        f"- Runtime request: `{audit['runtime_request']}`; observed models `{audit['observed_runtime']['response_models']}`; fingerprints `{audit['observed_runtime']['system_fingerprints']}`.",
        f"- HyDE cache/API: calls={audit['hyde_stats']['hyde_api_calls']}, hits={audit['hyde_stats']['hyde_cache_hits']}, records_after={audit['hyde_stats']['hyde_cache_records_after']}.",
        f"- Execution cache/API: calls={audit['execution_api_calls']}, hits={audit['execution_cache_hits']}, records_after={audit['execution_cache_records_after']}.",
        f"- Cold-run call budget: at most {audit['cold_run_call_budget']['hyde_generation_max_calls']} HyDE generation calls plus {audit['cold_run_call_budget']['execution_calls']} execution calls; latest reported calls are from the cache-replay command.",
        f"- Normalization changed predictions: {audit['normalization_changed_predictions']} / {audit['sample_n'] * len(audit['arms'])}.",
        "",
        "## Four-Arm Metrics",
        "",
        "| Arm | EM | F1 | Scale score | Parse failures | Invalid scale | Normalization failures |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in ARMS:
        r = audit["arm_metrics"][arm]
        lines.append(
            f"| `{arm}` | {fmt(r['exact_match'])} | {fmt(r['f1'])} | {fmt(r['scale_score'])} | "
            f"{r['parse_failures']} | {r['invalid_scale_parse_errors']} | {r['normalization_failures']} |"
        )
    lines.extend([
        "",
        f"Best Fixed: `{audit['best_fixed_arm']}` EM={fmt(audit['best_fixed_em'])}.",
        f"Sample Oracle EM={fmt(audit['sample_oracle_em'])}.",
        f"Oracle Gap={audit['oracle_gap']:+.3f}.",
        "",
        "## Memory Effect Events",
        "",
    ])
    for key, value in audit["event_counts"].items():
        lines.append(f"- `{key}`: {value}")
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
    interesting = [rec for rec in audit["records"] if 0 < len(rec["correct_arms_em"]) < 4][:10]
    lines.extend([
        "",
        "## Typical Non-Uniform Samples",
        "",
    ])
    for rec in interesting:
        preds = {arm: rec["outputs"][arm]["parsed"] for arm in ARMS}
        lines.append(
            f"- `{rec['sample_id']}` type={rec['answer_type']} scale={rec['scale'] or 'none'} correct={rec['correct_arms_em']} "
            f"question={rec['question'][:180]} predictions={preds}"
        )
    lines.extend([
        "",
        "## Decision",
        "",
        f"Decision: `{audit['decision']}`.",
    ])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Require HyDE and execution outputs to be cached.")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
