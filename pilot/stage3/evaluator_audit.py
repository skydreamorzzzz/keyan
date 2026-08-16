"""Audit official-compatible execution semantics.

Compares `pilot/executor.py` against `analysis/official_code/evaluate.py` on
gold FinQA programs, and recomputes Stage 2 official-aligned labels under both
strict official equality and the legacy relative-tolerance matcher.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from collections import Counter
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PILOT = os.path.join(ROOT, "pilot")
if PILOT not in sys.path:
    sys.path.insert(0, PILOT)

from executor import (  # noqa: E402
    exec_program_re,
    match_result,
    match_result_legacy,
    parse_linear_steps,
    program_tokenization,
)

OUT = os.path.join(PILOT, "stage3")
ARMS = {
    "none": "baseline",
    "case": "baseline_case",
    "strategy": "baseline_strategy",
    "both": "baseline_both",
}
STRUCT_ARMS = {
    "none": "structured",
    "case": "structured_case",
    "strategy": "structured_strategy",
    "both": "structured_both",
}


def load_official_eval():
    path = os.path.join(ROOT, "analysis", "official_code", "evaluate.py")
    spec = importlib.util.spec_from_file_location("official_finqa_evaluate", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def load_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def compare_gold_programs(split: str) -> dict[str, Any]:
    official = load_official_eval()
    data = load_json(os.path.join(ROOT, "data", "finqa", f"{split}.json"))
    mismatches = []
    official_gold_mismatches = 0
    for i, ex in enumerate(data):
        program = ex["qa"]["program"]
        table = ex["table"]
        gold = ex["qa"]["exe_ans"]
        off_invalid, off_res = official.eval_program(official.program_tokenization(program), table)
        ok, res = exec_program_re(program, table)
        strict = ok and match_result(res, gold)
        if off_invalid == 0 and off_res != gold:
            official_gold_mismatches += 1
        if bool(off_invalid == 0) != bool(ok) or off_res != (round(float(res), 5) if isinstance(res, (int, float)) else res) or strict != (off_invalid == 0 and off_res == gold):
            mismatches.append({
                "index": i,
                "id": ex.get("id"),
                "program": program,
                "official_invalid": off_invalid,
                "official_result": off_res,
                "local_ok": ok,
                "local_result": res,
                "gold": gold,
                "strict": strict,
            })
            if len(mismatches) >= 20:
                break
    return {
        "split": split,
        "n": len(data),
        "official_gold_mismatches": official_gold_mismatches,
        "local_vs_official_mismatch_count_first20": len(mismatches),
        "first_mismatches": mismatches,
    }


def arm_correct(raw: str, ex: dict[str, Any], legacy: bool = False) -> bool:
    ok, res = exec_program_re(raw, ex["table"])
    if not ok:
        return False
    matcher = match_result_legacy if legacy else match_result
    return matcher(res, ex["qa"]["exe_ans"])


def summarize_family(dev: list[dict[str, Any]], outs: dict[str, Any], arms: dict[str, str], legacy: bool = False) -> dict[str, Any]:
    per = []
    for i, ex in enumerate(dev):
        corr = {name: arm_correct(outs["prog"].get(arm, {}).get(str(i), ""), ex, legacy=legacy) for name, arm in arms.items()}
        per.append(corr)
    acc = {a: sum(c[a] for c in per) / len(per) for a in arms}
    best = max(acc.values())
    oracle = sum(any(c[a] for a in arms) for c in per) / len(per)
    return {
        "accuracy": acc,
        "best_fixed_arm": max(acc, key=acc.get),
        "best_fixed": best,
        "oracle": oracle,
        "oracle_gap": oracle - best,
        "case_beats_strategy": sum(c["case"] and not c["strategy"] for c in per),
        "strategy_beats_case": sum(c["strategy"] and not c["case"] for c in per),
        "both_wrong_single_correct": sum((not c["both"]) and (c["case"] or c["strategy"]) for c in per),
        "correct_set_distribution": {
            "+".join(cset) if cset else "none_correct": n
            for cset, n in Counter(tuple(a for a in arms if c[a]) for c in per).items()
        },
    }


def stage2_recompute() -> dict[str, Any]:
    dev = load_json(os.path.join(ROOT, "data", "finqa", "dev.json"))[:492]
    outs = load_json(os.path.join(PILOT, "stage2_official", "output", "arm_outputs.json"))
    return {
        "n": len(dev),
        "full_doc_strict": summarize_family(dev, outs, ARMS, legacy=False),
        "full_doc_legacy": summarize_family(dev, outs, ARMS, legacy=True),
        "structured_strict": summarize_family(dev, outs, STRUCT_ARMS, legacy=False),
        "structured_legacy": summarize_family(dev, outs, STRUCT_ARMS, legacy=True),
    }


def main() -> None:
    out = {
        "gold_program_audit": [compare_gold_programs("dev"), compare_gold_programs("train")],
        "stage2_recomputed": stage2_recompute(),
    }
    path = os.path.join(OUT, "evaluator_audit.json")
    json.dump(out, open(path, "w"), indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=2, ensure_ascii=False)[:12000])
    print(f"saved {path}")


if __name__ == "__main__":
    main()
