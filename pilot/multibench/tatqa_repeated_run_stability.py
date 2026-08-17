"""TAT-QA held-out repeated-run stability audit.

Uses the existing held-out diagnostic as rn1 and runs/loads independent rn2/rn3
execution caches. Retrieval, HyDE, memory, prompt, runtime request, and the
canonicalized evaluator are frozen.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
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
from tatqa_evaluator import raw_path  # noqa: E402
from tatqa_four_arm_dry_run import (  # noqa: E402
    ARMS,
    CONCURRENCY,
    MAX_TOKENS,
    SYSTEM,
    TEMPERATURE,
    ExecCache,
    build_prompt,
    dump_json,
    load_json,
    observed_runtime_summary,
    stable_hash,
)
from tatqa_heldout_four_arm_diagnostic import (  # noqa: E402
    AUDIT_JSON_PATH as RN1_JSON_PATH,
    METHOD_VERSION as HELDOUT_METHOD_VERSION,
    evaluate_outputs,
    event_counts,
    prepare_retrieval,
    select_heldout_sample,
    subset_gold_contexts,
)

OUT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "tatqa")
REPORT_PATH = os.path.join(OUT_DIR, "TATQA_REPEATED_RUN_STABILITY.md")
AUDIT_JSON_PATH = os.path.join(OUT_DIR, "tatqa_repeated_run_stability.json")
REPLICATES = ["rn1", "rn2", "rn3"]
NEW_REPLICATES = ["rn2", "rn3"]
METHOD_VERSION = "tatqa_repeated_run_stability_v1_fixed_heldout120"


def replicate_cache_path(replicate: str) -> str:
    return os.path.join(OUT_DIR, f"tatqa_heldout_repeated_run_{replicate}_cache.jsonl")


def repeated_cache_key(sample_index: int, record: dict[str, Any], arm: str, prompt: str, retrieval: dict[str, Any], replicate: str) -> str:
    return stable_hash({
        "version": METHOD_VERSION,
        "base_protocol_version": HELDOUT_METHOD_VERSION,
        "replicate": replicate,
        "sample_index": sample_index,
        "sample_id": record["sample_id"],
        "arm": arm,
        "runtime": llm.runtime_config(),
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "thinking_mode": False,
        "strategy_query_method": "frozen_hyde",
        "case_ids": [h["case_id"] for h in retrieval["case_hits"]],
        "strategy_ids": [h["strategy_id"] for h in retrieval["strategy_hits"]],
        "system": SYSTEM,
        "prompt": prompt,
    })


def rn1_from_existing() -> dict[str, Any]:
    rn1 = load_json(RN1_JSON_PATH)
    return {
        "replicate": "rn1",
        "source": os.path.relpath(RN1_JSON_PATH, ROOT),
        "arm_metrics": rn1["arm_metrics"],
        "event_counts": rn1["event_counts"],
        "records": rn1["records"],
        "observed_runtime": rn1.get("observed_runtime", {}),
        "execution_api_calls": 0,
        "execution_cache_hits": rn1.get("execution_cache_records_after", 0),
        "execution_cache_records_after": rn1.get("execution_cache_records_after", 0),
    }


def run_execution_replicate(replicate: str, dry_run: bool) -> dict[str, Any]:
    sample, _ = select_heldout_sample()
    retrieval, hyde_stats = prepare_retrieval(sample, dry_run=True)
    cache = ExecCache(replicate_cache_path(replicate))
    outputs: dict[str, dict[str, dict[str, Any]]] = {arm: {} for arm in ARMS}
    tasks = []
    for idx, rec in enumerate(sample):
        prep = retrieval[rec["sample_id"]]
        for arm in ARMS:
            prompt = build_prompt(rec, arm, prep["case_blocks"], prep["strategy_blocks"])
            key = repeated_cache_key(idx, rec, arm, prompt, prep, replicate)
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
            out, hit = fut.result()
            outputs[arm][uid] = out
            execution_calls += int(not hit)
            execution_hits += int(hit)

    gold_contexts = subset_gold_contexts({rec["native_question_uid"] for rec in sample})
    evaluated = evaluate_outputs(gold_contexts, outputs)
    details_by_arm = evaluated["details_by_arm"]
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

    return {
        "replicate": replicate,
        "source": os.path.relpath(replicate_cache_path(replicate), ROOT),
        "hyde_stats": hyde_stats,
        "arm_metrics": evaluated["arm_metrics"],
        "event_counts": event_counts(sample, details_by_arm),
        "records": records,
        "observed_runtime": observed_runtime_summary(outputs),
        "execution_api_calls": execution_calls,
        "execution_cache_hits": execution_hits,
        "execution_cache_records_after": len(cache.data),
    }


def correctness_table(runs: dict[str, dict[str, Any]]) -> dict[str, dict[str, dict[str, float]]]:
    table: dict[str, dict[str, dict[str, float]]] = {}
    for rep, run in runs.items():
        for rec in run["records"]:
            sid = rec["sample_id"]
            table.setdefault(sid, {arm: {} for arm in ARMS})
            for arm in ARMS:
                table[sid][arm][rep] = float(rec["outputs"][arm]["em"])
    return table


def expected_oracle_and_events(table: dict[str, dict[str, dict[str, float]]]) -> dict[str, Any]:
    p_correct = {
        sid: {arm: float(np.mean([by_rep[r] for r in REPLICATES])) for arm, by_rep in arms.items()}
        for sid, arms in table.items()
    }
    arm_means = {arm: float(np.mean([p_correct[sid][arm] for sid in p_correct])) for arm in ARMS}
    best_fixed_arm = max(ARMS, key=lambda arm: arm_means[arm])
    best_fixed = arm_means[best_fixed_arm]
    oracle = float(np.mean([max(p_correct[sid].values()) for sid in p_correct]))
    exclusive_best = Counter()
    for sid, vals in p_correct.items():
        best = max(vals.values())
        best_arms = [arm for arm, value in vals.items() if value == best]
        if len(best_arms) == 1:
            exclusive_best[f"{best_arms[0]}_only_expected_best"] += 1
    return {
        "p_correct": p_correct,
        "arm_means": arm_means,
        "best_fixed_arm": best_fixed_arm,
        "best_fixed_em": best_fixed,
        "expected_oracle_em": oracle,
        "expected_oracle_gap": oracle - best_fixed,
        "exclusive_expected_best_counts": dict(exclusive_best),
    }


def preference_event_stability(table: dict[str, dict[str, dict[str, float]]]) -> dict[str, Any]:
    specs = {
        "none_gt_both": ("none", "both"),
        "case_gt_both": ("case", "both"),
        "strategy_gt_both": ("strategy", "both"),
    }
    out = {}
    for name, (a, b) in specs.items():
        counts = []
        for arms in table.values():
            counts.append(sum(arms[a][r] > arms[b][r] for r in REPLICATES))
        out[name] = {
            "any_run": sum(c >= 1 for c in counts),
            "stable_2_of_3": sum(c >= 2 for c in counts),
            "stable_3_of_3": sum(c == 3 for c in counts),
        }
    return out


def correctness_flip_rates(table: dict[str, dict[str, dict[str, float]]]) -> dict[str, Any]:
    by_arm = {}
    for arm in ARMS:
        vals = []
        pairwise = []
        for arms in table.values():
            seq = [arms[arm][r] for r in REPLICATES]
            vals.append(len(set(seq)) > 1)
            pairwise.extend([seq[0] != seq[1], seq[0] != seq[2], seq[1] != seq[2]])
        by_arm[arm] = {
            "query_flip_count": int(sum(vals)),
            "query_flip_rate": float(np.mean(vals)),
            "pairwise_disagreement_rate": float(np.mean(pairwise)),
        }
    all_query_arm = [by_arm[arm]["query_flip_rate"] for arm in ARMS]
    return {"by_arm": by_arm, "mean_query_arm_flip_rate": float(np.mean(all_query_arm))}


def run(dry_run: bool = False, replicates: list[str] | None = None) -> dict[str, Any]:
    replicates = replicates or NEW_REPLICATES
    runs = {"rn1": rn1_from_existing()}
    for rep in replicates:
        if rep == "rn1":
            continue
        runs[rep] = run_execution_replicate(rep, dry_run=dry_run)
    if set(runs) != set(REPLICATES):
        missing = sorted(set(REPLICATES) - set(runs))
        raise RuntimeError(f"Missing replicates for full audit: {missing}")
    table = correctness_table(runs)
    expected = expected_oracle_and_events(table)
    pref_stability = preference_event_stability(table)
    flip_rates = correctness_flip_rates(table)
    run_best_fixed = {
        rep: max(ARMS, key=lambda arm: run["arm_metrics"][arm]["exact_match"])
        for rep, run in runs.items()
    }
    run_best_fixed_em = {rep: runs[rep]["arm_metrics"][run_best_fixed[rep]]["exact_match"] for rep in runs}
    audit = {
        "version": METHOD_VERSION,
        "sample_n": len(table),
        "replicates": REPLICATES,
        "frozen_protocol": {
            "sample": "existing TAT-QA held-out 120 sample from tatqa_heldout_four_arm_diagnostic.json",
            "retrieval": "frozen Case top-4 and frozen HyDE Strategy top-3",
            "prompt": "same build_prompt/SYSTEM as held-out diagnostic",
            "evaluator": "canonicalized TAT-QA prediction contract",
            "rn1_source": os.path.relpath(RN1_JSON_PATH, ROOT),
            "rn2_rn3_cache_namespace": METHOD_VERSION,
            "cold_run_note": "rn2/rn3 are independent execution cache namespaces. A cold run creates 480 records per replicate; latest API counters may be zero after cache replay.",
        },
        "runs": {
            rep: {
                "source": run["source"],
                "arm_metrics": run["arm_metrics"],
                "event_counts": run["event_counts"],
                "observed_runtime": run.get("observed_runtime", {}),
                "execution_api_calls": run.get("execution_api_calls", 0),
                "execution_cache_hits": run.get("execution_cache_hits", 0),
                "execution_cache_records_after": run.get("execution_cache_records_after", 0),
            }
            for rep, run in runs.items()
        },
        "run_best_fixed": run_best_fixed,
        "run_best_fixed_em": run_best_fixed_em,
        "mean_run_best_fixed_em": float(np.mean(list(run_best_fixed_em.values()))),
        "expected": expected,
        "preference_event_stability": pref_stability,
        "correctness_flip_rates": flip_rates,
        "decision": "TAT-QA HETEROGENEITY STABLE"
        if expected["expected_oracle_gap"] >= 0.04 and max(v["stable_2_of_3"] for v in pref_stability.values()) >= 5
        else "SIGNAL DOMINATED BY EXECUTION NOISE",
    }
    dump_json(AUDIT_JSON_PATH, audit)
    write_report(audit)
    print(json.dumps({
        "sample_n": audit["sample_n"],
        "run_arm_em": {rep: {arm: runs[rep]["arm_metrics"][arm]["exact_match"] for arm in ARMS} for rep in REPLICATES},
        "expected_best_fixed": expected["best_fixed_arm"],
        "expected_best_fixed_em": expected["best_fixed_em"],
        "expected_oracle_em": expected["expected_oracle_em"],
        "expected_oracle_gap": expected["expected_oracle_gap"],
        "preference_event_stability": pref_stability,
        "mean_flip_rate": flip_rates["mean_query_arm_flip_rate"],
        "decision": audit["decision"],
        "report": os.path.relpath(REPORT_PATH, ROOT),
    }, indent=2))
    return audit


def fmt(v: float) -> str:
    return f"{v:.3f}"


def write_report(audit: dict[str, Any]) -> None:
    lines = [
        "# TAT-QA Repeated-Run Stability",
        "",
        "Date: 2026-08-17",
        "",
        "Scope: repeated execution stability over the frozen 120-sample TAT-QA held-out diagnostic. rn1 is the existing held-out run; rn2/rn3 use independent execution cache namespaces. HyDE, retrieval, memory, prompt, runtime request, and canonicalized evaluator are frozen.",
        "",
        "## Runtime / Cache",
        "",
        "Note: the table below reports the latest command counters. After cache replay, calls are 0 and hits are 480; rn2/rn3 were first created in independent cold execution namespaces with 480 records each.",
        "",
    ]
    for rep in REPLICATES:
        r = audit["runs"][rep]
        lines.append(
            f"- `{rep}` source `{r['source']}`; calls={r['execution_api_calls']}; hits={r['execution_cache_hits']}; "
            f"records={r['execution_cache_records_after']}; observed models `{r.get('observed_runtime', {}).get('response_models', {})}`; "
            f"fingerprints `{r.get('observed_runtime', {}).get('system_fingerprints', {})}`."
        )
    lines.extend([
        "",
        "## Per-Run Four-Arm Metrics",
        "",
        "| Run | Arm | EM | F1 | Parse failures | Normalization failures |",
        "|---|---|---:|---:|---:|---:|",
    ])
    for rep in REPLICATES:
        for arm in ARMS:
            m = audit["runs"][rep]["arm_metrics"][arm]
            lines.append(f"| `{rep}` | `{arm}` | {fmt(m['exact_match'])} | {fmt(m['f1'])} | {m['parse_failures']} | {m['normalization_failures']} |")
    lines.extend([
        "",
        "## Best Fixed / Expected Oracle",
        "",
        f"- Per-run Best Fixed arms: `{audit['run_best_fixed']}`.",
        f"- Mean per-run Best Fixed EM: {fmt(audit['mean_run_best_fixed_em'])}.",
        f"- 3-run p_correct Best Fixed: `{audit['expected']['best_fixed_arm']}` EM={fmt(audit['expected']['best_fixed_em'])}.",
        f"- 3-run p_correct Oracle EM={fmt(audit['expected']['expected_oracle_em'])}.",
        f"- 3-run p_correct Oracle Gap={audit['expected']['expected_oracle_gap']:+.3f}.",
        f"- Exclusive expected-best counts: `{audit['expected']['exclusive_expected_best_counts']}`.",
        "",
        "## One-Shot Event Counts By Run",
        "",
        "| Run | Case-only | Strategy-only | Both-only | None-only | None>Both | Case>Both | Strategy>Both |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for rep in REPLICATES:
        e = audit["runs"][rep]["event_counts"]
        lines.append(f"| `{rep}` | {e['case_only']} | {e['strategy_only']} | {e['both_only']} | {e['none_only']} | {e['none_gt_both']} | {e['case_gt_both']} | {e['strategy_gt_both']} |")
    lines.extend([
        "",
        "## Preference-Event Stability",
        "",
        "| Event | Any run | >=2/3 runs | 3/3 runs |",
        "|---|---:|---:|---:|",
    ])
    for name, vals in audit["preference_event_stability"].items():
        lines.append(f"| `{name}` | {vals['any_run']} | {vals['stable_2_of_3']} | {vals['stable_3_of_3']} |")
    lines.extend([
        "",
        "## Correctness Flip Rate",
        "",
        "| Arm | Query flip count | Query flip rate | Pairwise disagreement rate |",
        "|---|---:|---:|---:|",
    ])
    for arm, vals in audit["correctness_flip_rates"]["by_arm"].items():
        lines.append(f"| `{arm}` | {vals['query_flip_count']} | {fmt(vals['query_flip_rate'])} | {fmt(vals['pairwise_disagreement_rate'])} |")
    lines.extend([
        "",
        f"Mean query-arm flip rate: {fmt(audit['correctness_flip_rates']['mean_query_arm_flip_rate'])}.",
        "",
        "## Interpretation",
        "",
        "- Overall arm correctness is noisy across single executions, so one-shot event counts should not be read as stable selector labels.",
        "- The p_correct oracle measures repeated-run expected heterogeneity under the frozen runtime and canonicalized evaluator.",
        "- Preference-event stability focuses on selector-relevant deviations from Both, especially None/Case/Strategy outperforming Both.",
        "",
        "## Decision",
        "",
        f"Decision: `{audit['decision']}`.",
    ])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Require rn2/rn3 execution caches to exist.")
    parser.add_argument("--replicates", nargs="+", default=NEW_REPLICATES)
    args = parser.parse_args()
    run(dry_run=args.dry_run, replicates=args.replicates)


if __name__ == "__main__":
    main()
