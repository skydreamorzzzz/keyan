"""Generate inference-safe mechanism features for Stage 4A.

One fixed-schema DeepSeek call per query. The prompt never includes correctness,
gold answer, gold program, oracle labels, or gold operation annotations.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "stage2_official"))

import llm  # noqa: E402
import s2o_common as c  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.dirname(__file__)
CACHE_PATH = os.path.join(OUT, "synthetic_feature_cache.jsonl")
OUT_JSONL = os.path.join(OUT, "synthetic_features.jsonl")
OUT_JSON = os.path.join(OUT, "synthetic_features.json")
CACHE_VERSION = "stage4a_synthetic_mechanism_v1"
MAX_CONTEXT_CHARS = 6000

SCHEMA = {
    "ratio_likelihood": "0..1",
    "change_likelihood": "0..1",
    "aggregation_likelihood": "0..1",
    "comparison_likelihood": "0..1",
    "arithmetic_depth": "1..4",
    "percent_or_ratio_output": "0..1",
    "absolute_value_output": "0..1",
    "unit_scale_risk": "0..1",
    "table_heavy_reasoning": "0..1",
    "ambiguity_risk": "0..1",
    "case_applicability": "0..1",
    "case_operation_compatibility": "0..1",
    "case_scale_compatibility": "0..1",
    "case_copy_risk": "0..1",
    "strategy_applicability": "0..1",
    "strategy_operation_compatibility": "0..1",
    "strategy_scale_compatibility": "0..1",
    "strategy_conflict_risk": "0..1",
    "case_strategy_agreement": "0..1",
    "combination_overload_risk": "0..1",
}

SYSTEM = (
    "You produce inference-time-safe semantic features for financial QA routing. "
    "Do not answer the question. Do not infer from any gold answer or labels. "
    "Return only valid JSON with numeric values in the requested schema."
)


def load_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def load_records() -> list[dict[str, Any]]:
    return [json.loads(line) for line in open(os.path.join(OUT, "marginal_utility_dataset.jsonl"))]


def sanitize_case(case: dict[str, Any]) -> dict[str, Any]:
    return {k: case.get(k) for k in ["rank", "score", "problem_kind", "n_steps", "struct", "operation_family", "question", "exe_ans"]}


def sanitize_strategy(strategy: dict[str, Any]) -> dict[str, Any]:
    return {k: strategy.get(k) for k in ["rank", "score", "case_hits", "name", "problem_pattern", "canonical_output_scale", "program_family"]}


def prompt_for(rec: dict[str, Any], dev: list[dict[str, Any]]) -> str:
    ex = dev[rec["sample_index"]]
    context, question, _ = c.finqa_normalize(ex)
    context = context[:MAX_CONTEXT_CHARS]
    payload = {
        "task": "Score mechanism features only. Do not choose an arm and do not solve.",
        "question": question,
        "context_truncated": context,
        "retrieved_cases": [sanitize_case(x) for x in rec["retrieval_sanitized"]["case"]],
        "retrieved_strategies": [sanitize_strategy(x) for x in rec["retrieval_sanitized"]["strategy"]],
        "schema": SCHEMA,
        "scale_guidance": "High unit_scale_risk means percent/fraction/raw-unit convention is easy to confuse between query and memories.",
        "output_contract": "Return a single JSON object with exactly the schema keys and numeric values only.",
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def stable_key(prompt: str) -> str:
    payload = {
        "version": CACHE_VERSION,
        "runtime": llm.runtime_config(),
        "system": SYSTEM,
        "prompt": prompt,
        "schema": SCHEMA,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def parse_json(text: str) -> dict[str, float]:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"no JSON object in response: {text[:200]}")
    raw = json.loads(m.group(0))
    out = {}
    for key in SCHEMA:
        val = float(raw.get(key, 0.0))
        if key == "arithmetic_depth":
            val = max(1.0, min(4.0, val))
        else:
            val = max(0.0, min(1.0, val))
        out[key] = val
    return out


class Cache:
    def __init__(self, path: str):
        self.path = path
        self.data = {}
        self.expected_runtime = None
        if os.path.exists(path):
            for line in open(path):
                rec = json.loads(line)
                self.data[rec["key"]] = rec
                runtime = rec.get("runtime")
                if runtime and self.expected_runtime is None:
                    self.expected_runtime = runtime

    def validate_runtime(self, runtime: dict[str, Any]) -> None:
        if self.expected_runtime is None:
            self.expected_runtime = runtime
            return
        keys = ["response_model", "effective_model", "system_fingerprint", "thinking_mode", "temperature", "max_tokens"]
        drift = {k: (self.expected_runtime.get(k), runtime.get(k)) for k in keys if self.expected_runtime.get(k) != runtime.get(k)}
        if drift:
            raise RuntimeError(f"synthetic feature runtime drift detected; start new namespace. drift={drift}")

    def call(self, key: str, prompt: str) -> dict[str, Any]:
        if key in self.data:
            return self.data[key]
        response = llm.call_once_with_metadata(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            max_tokens=800,
            timeout=180,
        )
        self.validate_runtime(response["runtime"])
        features = parse_json(response["text"])
        rec = {"key": key, "features": features, "raw_response": response["text"], "runtime": response["runtime"]}
        with open(self.path, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.data[key] = rec
        return rec


def generate() -> list[dict[str, Any]]:
    records = load_records()
    dev = load_json(os.path.join(ROOT, "data", "finqa", "dev.json"))
    cache = Cache(CACHE_PATH)
    outputs = []
    for j, rec in enumerate(records, 1):
        prompt = prompt_for(rec, dev)
        key = stable_key(prompt)
        cached = cache.call(key, prompt)
        outputs.append({
            "sample_index": rec["sample_index"],
            "sample_id": rec["sample_id"],
            "annual_report_group": rec["annual_report_group"],
            "features": cached["features"],
            "runtime": cached.get("runtime", {}),
            "cache_key": key,
            "raw_response": cached.get("raw_response", ""),
        })
        if j % 25 == 0:
            print(f"{j}/{len(records)}")
    json.dump(outputs, open(OUT_JSON, "w"), indent=2, ensure_ascii=False)
    with open(OUT_JSONL, "w") as f:
        for rec in outputs:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"saved {len(outputs)} synthetic feature records")
    return outputs


if __name__ == "__main__":
    generate()
