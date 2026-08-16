"""Confirm frozen Stage 4B router on public FinQA test holdout.

Frozen router is conservative no-override, so only Both is executed.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from statistics import mean
from typing import Any

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stage2_official"))

import llm  # noqa: E402
import retrieval as pilot_retrieval  # noqa: E402
import s2o_common as c  # noqa: E402
from executor import exec_program_re, match_result  # noqa: E402
from run_official import SYS_PROGRAM, exp_block  # noqa: E402
from stage4b_common import annual_report_group, cluster_bootstrap, estimate_tokens, load_json  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.dirname(__file__)
TOP_CASE = 4
TOP_STRATEGY = 3
CACHE_VERSION = "stage4b_holdout_both_v1"


def holdout_indices() -> dict[str, Any]:
    train = load_json(os.path.join(ROOT, "data", "finqa", "train.json"))
    dev = load_json(os.path.join(ROOT, "data", "finqa", "dev.json"))[:492]
    test = load_json(os.path.join(ROOT, "data", "finqa", "test.json"))
    train_reports = {annual_report_group(x) for x in train}
    dev_reports = {annual_report_group(x) for x in dev}
    keep = [i for i, ex in enumerate(test) if annual_report_group(ex) not in train_reports and annual_report_group(ex) not in dev_reports]
    audit = {
        "rule": "public test annual_report_group disjoint from train.json and dev[:492]",
        "test_n": len(test),
        "test_annual_reports": len({annual_report_group(x) for x in test}),
        "train_annual_reports": len(train_reports),
        "dev492_annual_reports": len(dev_reports),
        "primary_indices": keep,
        "primary_n": len(keep),
        "primary_annual_reports": len({annual_report_group(test[i]) for i in keep}),
    }
    json.dump(audit, open(os.path.join(OUT, "holdout_audit.json"), "w"), indent=2)
    return audit


def build_prep(indices: list[int]) -> dict[int, dict[str, Any]]:
    test = load_json(os.path.join(ROOT, "data", "finqa", "test.json"))
    case_mem = {x["case_id"]: x for x in load_json(os.path.join(ROOT, "pilot", "output", "case_memory.json"))}
    strat_by_id = {s["strategy_id"]: s for s in load_json(os.path.join(ROOT, "pilot", "output", "strategies_clean.json"))}
    pilot_retrieval._load_meta()
    prep = {}
    for i in indices:
        ex = test[i]
        context, question, _ = c.finqa_normalize(ex)
        rc = pilot_retrieval.retrieve_cases(question, TOP_CASE)
        rs = pilot_retrieval.retrieve_strategies_v2(question, TOP_STRATEGY)
        case_blocks = []
        for r in rc:
            cc = case_mem[r["case_id"]]
            facts = " ; ".join(cc["gold_facts"][:3])
            case_blocks.append(f"Case {cc['case_id']}: Q={cc['question']} | Facts={facts} | Prog={cc['program_re']} | Ans={cc['exe_ans']}")
        strat_blocks = []
        for r in rs:
            s = strat_by_id[r["strategy_id"]]
            strat_blocks.append(f"Strategy {s['name']}: pattern={s['problem_pattern']} | roles={s['operand_roles']} | template={s['template']} | scale={s['canonical_output_scale']}")
        memory = exp_block(case_blocks, strat_blocks)
        prompt = "CONTEXT:\n" + context + memory + f"\n\nQUESTION:\n{question}\n\nPROGRAM:"
        no_mem_prompt = "CONTEXT:\n" + context + f"\n\nQUESTION:\n{question}\n\nPROGRAM:"
        case_prompt = "CONTEXT:\n" + context + exp_block(case_blocks, None) + f"\n\nQUESTION:\n{question}\n\nPROGRAM:"
        strategy_prompt = "CONTEXT:\n" + context + exp_block(None, strat_blocks) + f"\n\nQUESTION:\n{question}\n\nPROGRAM:"
        prep[i] = {
            "prompt": prompt,
            "system": SYS_PROGRAM,
            "token_cost": {
                "none_prompt_tokens": estimate_tokens(no_mem_prompt),
                "case_prompt_tokens": estimate_tokens(case_prompt),
                "strategy_prompt_tokens": estimate_tokens(strategy_prompt),
                "both_prompt_tokens": estimate_tokens(prompt),
                "none_memory_tokens": 0,
                "case_memory_tokens": max(0, estimate_tokens(case_prompt) - estimate_tokens(no_mem_prompt)),
                "strategy_memory_tokens": max(0, estimate_tokens(strategy_prompt) - estimate_tokens(no_mem_prompt)),
                "both_memory_tokens": max(0, estimate_tokens(prompt) - estimate_tokens(no_mem_prompt)),
            },
        }
    return prep


class Cache:
    def __init__(self, path: str):
        self.path = path
        self.data = {}
        self.expected_runtime = None
        if os.path.exists(path):
            for line in open(path):
                rec = json.loads(line)
                self.data[rec["key"]] = rec
                if rec.get("runtime") and self.expected_runtime is None:
                    self.expected_runtime = rec["runtime"]

    def validate(self, runtime: dict[str, Any]) -> None:
        if self.expected_runtime is None:
            self.expected_runtime = runtime
            return
        keys = ["response_model", "effective_model", "system_fingerprint", "thinking_mode", "temperature", "max_tokens"]
        drift = {k: (self.expected_runtime.get(k), runtime.get(k)) for k in keys if self.expected_runtime.get(k) != runtime.get(k)}
        if drift:
            raise RuntimeError(f"holdout runtime drift detected: {drift}")

    def call(self, key: str, prompt: str, system: str) -> dict[str, Any]:
        if key in self.data:
            return self.data[key]
        response = llm.call_once_with_metadata(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=600,
            timeout=180,
        )
        self.validate(response["runtime"])
        rec = {"key": key, "out": response["text"], "runtime": response["runtime"]}
        with open(self.path, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.data[key] = rec
        return rec


def stable_key(rep: str, sample_index: int, prompt: str, system: str) -> str:
    payload = {
        "version": CACHE_VERSION,
        "replicate": rep,
        "dataset": "test",
        "sample_index": sample_index,
        "action": "both",
        "runtime": llm.runtime_config(),
        "retrieval": {"case_top_k": TOP_CASE, "strategy_top_k": TOP_STRATEGY},
        "system": system,
        "prompt": prompt,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def run(replicates: list[str] = ["h1", "h2"]) -> dict[str, Any]:
    os.makedirs(OUT, exist_ok=True)
    audit = holdout_indices()
    indices = audit["primary_indices"]
    prep = build_prep(indices)
    test = load_json(os.path.join(ROOT, "data", "finqa", "test.json"))
    all_results = {}
    for rep in replicates:
        cache = Cache(os.path.join(OUT, f"holdout_both_cache_{rep}.jsonl"))
        outputs = {}
        for j, i in enumerate(indices, 1):
            key = stable_key(rep, i, prep[i]["prompt"], prep[i]["system"])
            outputs[str(i)] = cache.call(key, prep[i]["prompt"], prep[i]["system"])
            if j % 20 == 0:
                print(f"{rep}: {j}/{len(indices)}")
        all_results[rep] = outputs
    evals = {}
    for rep, outs in all_results.items():
        correct = {}
        for i in indices:
            raw = outs[str(i)]["out"]
            ok, res = exec_program_re(raw, test[i]["table"])
            correct[i] = bool(ok and match_result(res, test[i]["qa"]["exe_ans"]))
        diffs = {pos: 0.0 for pos, _ in enumerate(indices)}
        pseudo_records = [{"annual_report_group": annual_report_group(test[i])} for i in indices]
        evals[rep] = {
            "both_accuracy": float(mean(correct.values())),
            "router_accuracy": float(mean(correct.values())),
            "gain_vs_both": 0.0,
            "deviation_coverage": 0.0,
            "cluster_bootstrap": cluster_bootstrap(diffs, pseudo_records, "annual_report_group"),
        }
    token_cost = {
        "avg_none_prompt_tokens": float(mean(prep[i]["token_cost"]["none_prompt_tokens"] for i in indices)),
        "avg_case_prompt_tokens": float(mean(prep[i]["token_cost"]["case_prompt_tokens"] for i in indices)),
        "avg_strategy_prompt_tokens": float(mean(prep[i]["token_cost"]["strategy_prompt_tokens"] for i in indices)),
        "avg_both_prompt_tokens": float(mean(prep[i]["token_cost"]["both_prompt_tokens"] for i in indices)),
        "avg_none_memory_tokens": 0.0,
        "avg_case_memory_tokens": float(mean(prep[i]["token_cost"]["case_memory_tokens"] for i in indices)),
        "avg_strategy_memory_tokens": float(mean(prep[i]["token_cost"]["strategy_memory_tokens"] for i in indices)),
        "avg_both_memory_tokens": float(mean(prep[i]["token_cost"]["both_memory_tokens"] for i in indices)),
        "frozen_router_avg_memory_tokens": float(mean(prep[i]["token_cost"]["both_memory_tokens"] for i in indices)),
        "frozen_router_avg_prompt_tokens": float(mean(prep[i]["token_cost"]["both_prompt_tokens"] for i in indices)),
    }
    out = {"holdout_audit": audit, "replicate_evaluation": evals, "token_cost": token_cost}
    json.dump(out, open(os.path.join(OUT, "holdout_confirmation.json"), "w"), indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=2)[:4000])
    return out


if __name__ == "__main__":
    run()
