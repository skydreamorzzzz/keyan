"""Repeated-run marginal utility stability experiment.

Runs Full-doc official-aligned program arms on a deterministic 250-query subset.
Each replicate uses an independent cache namespace and never reads the Stage 2
LLM cache. The old Stage 2 output can be used later only as historical run0.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stage2_official"))

import config as pilot_config  # noqa: E402
import llm as pilot_llm  # noqa: E402
import retrieval as pilot_retrieval  # noqa: E402
import s2o_common as c  # noqa: E402
from run_official import SYS_PROGRAM, exp_block  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "stability")
N = 492
SAMPLE_N = 250
TOP_CASE = 4
TOP_STRATEGY = 3
ARMS = {
    "none": "baseline",
    "case": "baseline_case",
    "strategy": "baseline_strategy",
    "both": "baseline_both",
}
CACHE_VERSION = "stability_full_doc_prog_v1"


def load_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def deterministic_subset(dev: list[dict[str, Any]], n: int = SAMPLE_N) -> list[int]:
    ranked = []
    for i, ex in enumerate(dev[:N]):
        sid = str(ex.get("id", i))
        h = hashlib.sha256(f"stage3-stability-v1|{i}|{sid}".encode()).hexdigest()
        ranked.append((h, i))
    return [i for _, i in sorted(ranked)[:n]]


def stable_key(replicate: str, arm: str, sample_index: int, prompt: str, system: str) -> str:
    payload = {
        "version": CACHE_VERSION,
        "replicate": replicate,
        "mode": "prog",
        "arm": arm,
        "sample_index": sample_index,
        "llm_runtime": pilot_llm.runtime_config(),
        "model": pilot_config.LLM_MODEL,
        "temperature": pilot_config.LLM_TEMPERATURE,
        "max_tokens": 600,
        "thinking": "disabled",
        "system": system,
        "prompt": prompt,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class JsonlCache:
    def __init__(self, path: str):
        self.path = path
        self.cache = {}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            for line in open(path):
                try:
                    rec = json.loads(line)
                    self.cache[rec["key"]] = rec["out"]
                except Exception:
                    pass

    def call(self, key: str, prompt: str, system: str) -> str:
        if key in self.cache:
            return self.cache[key]
        out = c.ask_llm(prompt, system=system)
        self.cache[key] = out
        with open(self.path, "a") as f:
            f.write(json.dumps({"key": key, "out": out}, ensure_ascii=False) + "\n")
        return out


def build_prep(dev: list[dict[str, Any]], sample_indices: list[int]) -> dict[int, dict[str, Any]]:
    case_mem = {x["case_id"]: x for x in load_json(os.path.join(os.path.dirname(__file__), "..", "output", "case_memory.json"))}
    strat_by_id = {s["strategy_id"]: s for s in load_json(os.path.join(os.path.dirname(__file__), "..", "output", "strategies_clean.json"))}
    pilot_retrieval._load_meta()
    prep = {}
    for i in sample_indices:
        ex = dev[i]
        context, question, gold = c.finqa_normalize(ex)
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
        prep[i] = {
            "context": context,
            "question": question,
            "gold": gold,
            "case_blocks": case_blocks,
            "strat_blocks": strat_blocks,
        }
    return prep


def prompt_for(p: dict[str, Any], arm: str) -> tuple[str, str]:
    if arm == "both":
        e = exp_block(p["case_blocks"], p["strat_blocks"])
    elif arm == "case":
        e = exp_block(p["case_blocks"], None)
    elif arm == "strategy":
        e = exp_block(None, p["strat_blocks"])
    else:
        e = ""
    return "CONTEXT:\n" + p["context"] + e + f"\n\nQUESTION:\n{p['question']}\n\nPROGRAM:", SYS_PROGRAM


def run(replicate: str, workers: int) -> None:
    os.makedirs(OUT, exist_ok=True)
    dev = load_json(os.path.join(c.DATA, "dev.json"))[:N]
    sample_indices = deterministic_subset(dev)
    sample_path = os.path.join(OUT, "sample_indices.json")
    if not os.path.exists(sample_path):
        json.dump({
            "rule": "sha256('stage3-stability-v1|{sample_index}|{sample_id}') sorted ascending, first 250 of official dev[:492]",
            "n": len(sample_indices),
            "indices": sample_indices,
        }, open(sample_path, "w"), indent=2)
    prep = build_prep(dev, sample_indices)
    out_path = os.path.join(OUT, f"stability_run_{replicate}.json")
    results = load_json(out_path) if os.path.exists(out_path) else {"replicate": replicate, "prog": {a: {} for a in ARMS.values()}}
    cache = JsonlCache(os.path.join(OUT, f"llm_cache_stability_{replicate}.jsonl"))

    pending = []
    for i in sample_indices:
        for logical, arm in ARMS.items():
            results["prog"].setdefault(arm, {})
            if str(i) in results["prog"][arm]:
                continue
            prompt, system = prompt_for(prep[i], logical)
            key = stable_key(replicate, arm, i, prompt, system)
            pending.append((i, arm, key, prompt, system))
    print(f"replicate={replicate} sample_n={len(sample_indices)} pending={len(pending)}")

    def work(item):
        i, arm, key, prompt, system = item
        return i, arm, cache.call(key, prompt, system)

    failures = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for j, item in enumerate(ex.map(work, pending), 1):
            i, arm, out = item
            if out is None:
                failures.append((i, arm))
                continue
            results["prog"][arm][str(i)] = out
            if j % 20 == 0:
                json.dump(results, open(out_path, "w"), ensure_ascii=False)
                print(f"  {j}/{len(pending)}")
    results["failures"] = failures
    json.dump(results, open(out_path, "w"), ensure_ascii=False)
    print(f"saved {out_path} failures={len(failures)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--replicate", required=True)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    run(args.replicate, args.workers)
