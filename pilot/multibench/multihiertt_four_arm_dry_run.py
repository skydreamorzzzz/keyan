"""MultiHiertt Four-Arm Dry-Run — Stage 33.

Scientific question: Given retrieval protocol from Stage 32 (question_only + family-dedup
top-k=10), does Strategy Memory improve downstream accuracy? Does it interfere when
retrieval misses?

Arms: none / case / strategy / both
Retrieval:
  - Case: full-context query (make_target_retrieval_text), top-4, source_id exclusion
  - Strategy: question_only query + family-dedup top-3 from k=10 (Stage 32 protocol)
Sample: first 60 of fixed 120-sample validation set (seed 20260817)
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import random
import re
import sys
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import numpy as np
import pyarrow.parquet as pq

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PILOT_DIR = os.path.join(ROOT, "pilot")
if PILOT_DIR not in sys.path:
    sys.path.insert(0, PILOT_DIR)
if os.path.dirname(__file__) not in sys.path:
    sys.path.insert(0, os.path.dirname(__file__))

import config  # noqa: E402
import llm  # noqa: E402
from retrieval import get_model  # noqa: E402
from multihiertt_case_memory import (  # noqa: E402
    CASE_MEMORY_PATH,
    CASE_EMB_PATH,
    CASE_ORDER_PATH,
    make_target_retrieval_text,
    retrieve_cases,
)
from multihiertt_evaluator import evaluate_rows  # noqa: E402
from multihiertt_strategy_structure_audit import abstract_record, load_rows  # noqa: E402
from multihiertt_strategy_memory_pilot import strategy_type as strategy_type_label  # noqa: E402

STRATEGY_MEMORY_PATH = os.path.join(ROOT, "data", "multihiertt", "processed", "multihiertt_strategy_memory_v0.json")
OUT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "multihiertt")
REPORT_STEM = "MULTIHIERTT_FOUR_ARM_DRY_RUN_REPAIRED"
JSON_STEM = "multihiertt_four_arm_dry_run_repaired"

VERSION = "multihiertt_four_arm_dry_run_v3_repaired_runtime_json_20260818"
SEED = 20260817
FULL_SAMPLE_N = 120
DEFAULT_SAMPLE_N = 60
CASE_TOP_K = 4
STRATEGY_TOP_K_EXPAND = 10
ARMS = ["none", "case", "strategy", "both"]
MAX_TOKENS = 1400
TEMPERATURE = 0
CONCURRENCY = 2
RESPONSE_FORMAT = {"type": "json_object"}
PARSE_MAX_RETRIES = 3
EXPECTED_RUNTIME = {
    "backend": "deepseek_openai_compatible",
    "base_url": "https://api.deepseek.com",
    "requested_model": "deepseek-v4-flash",
    "response_model": "deepseek-v4-flash",
    "thinking_mode": False,
}


def artifact_paths(cache_suffix: str = "") -> dict[str, str]:
    suffix = f"_{cache_suffix}" if cache_suffix else ""
    return {
        "report": os.path.join(OUT_DIR, f"{REPORT_STEM}{suffix}.md"),
        "json": os.path.join(OUT_DIR, f"{JSON_STEM}{suffix}.json"),
        "cache": os.path.join(OUT_DIR, f"{JSON_STEM}{suffix}_cache.jsonl"),
    }


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def count_jsonl(path: str) -> int:
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


# ── Strategy retrieval: Stage 32 protocol ────────────────────────────────────

def embed_strategies(strategies: list[dict[str, Any]]) -> np.ndarray:
    model = get_model()
    texts = [s["retrieval_text"] for s in strategies]
    return model.encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True)


def retrieve_strategies_qonly_dedup(
    question: str,
    strategies: list[dict[str, Any]],
    emb: np.ndarray,
    k_expand: int = STRATEGY_TOP_K_EXPAND,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """Stage 32 protocol: question-only query, family-dedup, top-3 distinct families."""
    model = get_model()
    q = model.encode([question], normalize_embeddings=True)[0]
    sims = emb @ q
    idx = np.argsort(-sims)[:k_expand]
    top10 = []
    for i in idx:
        s = strategies[int(i)]
        top10.append({
            "strategy_id": s["strategy_id"],
            "family": s["family"],
            "strategy_type": s["strategy_type"],
            "schema_key": s["schema_key"],
            "score": float(sims[int(i)]),
        })
    # family-dedup: keep best score per family
    seen: dict[str, dict[str, Any]] = {}
    for h in top10:
        fam = h["family"]
        if fam not in seen or h["score"] > seen[fam]["score"]:
            seen[fam] = h
    deduped = sorted(seen.values(), key=lambda x: -x["score"])[:top_n]
    return deduped


# ── Context rendering ─────────────────────────────────────────────────────────

def render_table_html_preview(html: str, limit: int = 600) -> str:
    return normalize_text(html)[:limit]


def render_context(row: dict[str, Any]) -> str:
    paragraphs = []
    for i, text in enumerate((row.get("paragraphs") or [])[:30]):
        t = normalize_text(text)
        if len(t) > 300:
            t = t[:300].rstrip() + "..."
        paragraphs.append(f"p{i}: {t}")
    table_bits = []
    for i, html in enumerate((row.get("tables") or [])[:6]):
        table_bits.append(f"table_{i}: {render_table_html_preview(html)}")
    return "\n".join([
        "Paragraphs (selected):",
        "\n".join(paragraphs) or "(none)",
        "",
        "Tables (HTML preview):",
        "\n".join(table_bits) or "(none)",
    ]).strip()


def short_case_block(case: dict[str, Any], score: float) -> str:
    q = normalize_text(case.get("question", ""))
    prog = normalize_text(case.get("program", ""))
    ans = normalize_text(str(case.get("answer", "")))
    text_ev = " ; ".join(
        normalize_text(e.get("text", ""))[:200]
        for e in (case.get("text_evidence_resolved") or [])[:2]
        if e.get("text")
    )
    table_ev = " ; ".join(
        f"{e.get('cell_ref')}: {normalize_text(e.get('description',''))[:120]}"
        for e in (case.get("table_evidence_resolved") or [])[:4]
        if e.get("cell_ref")
    )
    lines = [
        f"[Case {case['case_id']} score={score:.3f}]",
        f"Q: {q}",
        f"Program: {prog}" if prog else "",
        f"Answer: {ans}",
        f"Evidence text: {text_ev}" if text_ev else "",
        f"Evidence table: {table_ev}" if table_ev else "",
    ]
    return "\n".join(l for l in lines if l)


def short_strategy_block(strategy: dict[str, Any], score: float) -> str:
    lines = [
        f"[Strategy {strategy['strategy_id']} score={score:.3f}]",
        f"Family: {strategy['family']}  Type: {strategy['strategy_type']}",
        f"Description: {normalize_text(strategy.get('description', ''))[:300]}",
        "Reasoning: " + " ; ".join(
            normalize_text(g)[:160] for g in (strategy.get("reasoning_guidance") or [])[:2]
        ),
        "Evidence: " + " ; ".join(
            normalize_text(g)[:160] for g in (strategy.get("evidence_guidance") or [])[:2]
        ),
        "Operands: " + " ; ".join(
            normalize_text(r)[:120] for r in (strategy.get("operand_roles") or [])[:3]
        ),
        f"Answer form: {normalize_text(strategy.get('answer_form', ''))[:120]}",
        "Scale notes: " + " ; ".join(
            normalize_text(n)[:100] for n in (strategy.get("scale_notes") or [])[:2]
        ),
        "Risks: " + " ; ".join(
            normalize_text(r)[:100] for r in (strategy.get("risk_notes") or [])[:2]
        ),
    ]
    return "\n".join(l for l in lines if l)


def build_memory_section(arm: str, case_blocks: list[str], strategy_blocks: list[str]) -> str:
    parts = []
    if arm in {"case", "both"} and case_blocks:
        parts.append(
            "SIMILAR SOLVED CASES\n"
            "Use these for analogous reasoning structure and evidence location. "
            "Do not copy numbers from cases into your answer.\n"
            + "\n\n".join(case_blocks)
        )
    if arm in {"strategy", "both"} and strategy_blocks:
        parts.append(
            "RETRIEVED REASONING STRATEGIES\n"
            "Apply the most relevant strategy if it matches the question structure. "
            "Ignore strategies that do not match.\n"
            + "\n\n".join(strategy_blocks)
        )
    return "\n\n".join(parts)


SYSTEM = (
    "You answer MultiHiertt financial reasoning questions. "
    "The question may require reading one or more hierarchical HTML tables and text passages. "
    "Return ONLY valid JSON with key \"answer\" (string, number, or list). "
    "Do not include explanations outside the JSON."
)


def build_prompt(row: dict[str, Any], arm: str, case_blocks: list[str], strategy_blocks: list[str]) -> str:
    payload = {
        "task": "Answer the MultiHiertt financial question. Use the context and optional memory only as support.",
        "question": row.get("question", ""),
        "context": render_context(row),
        "memory": build_memory_section(arm, case_blocks, strategy_blocks),
        "output_contract": {
            "answer": "string, number, or list — the final answer value only",
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def parse_answer(text: str) -> tuple[Any, str | None]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        raw = json.loads(cleaned)
        if not isinstance(raw, dict):
            return None, "json_not_object"
        return raw.get("answer"), None
    except Exception as exc:  # noqa: BLE001
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", cleaned):
            try:
                raw, _ = decoder.raw_decode(cleaned[match.start():])
            except Exception:
                continue
            if isinstance(raw, dict) and "answer" in raw:
                return raw.get("answer"), None
        if "{" not in cleaned:
            return None, "no_json"
        fallback = re.match(r'^\s*\{\s*"answer"\s*:\s*(.*?)\s*\}\s*$', cleaned, flags=re.S)
        if fallback:
            raw_value = fallback.group(1).strip()
            if (
                (raw_value.startswith('"') and raw_value.endswith('"'))
                or (raw_value.startswith("'") and raw_value.endswith("'"))
            ):
                raw_value = raw_value[1:-1]
            elif raw_value.endswith('"') or raw_value.endswith("'"):
                raw_value = raw_value[:-1].rstrip()
            elif raw_value.startswith('"') or raw_value.startswith("'"):
                raw_value = raw_value[1:].lstrip()
            return raw_value, None
        return None, f"parse_error:{type(exc).__name__}"


# ── Execution cache ───────────────────────────────────────────────────────────

class ExecCache:
    def __init__(self, path: str):
        self.path = path
        self.data: dict[str, dict[str, Any]] = {}
        self.fingerprint: str | None = None
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rec = json.loads(line)
                            self.validate_record(rec, from_cache=True)
                            self.data[rec["key"]] = rec
                        except Exception:
                            raise RuntimeError(f"Invalid execution cache record in {path}")

    def validate_runtime(self, runtime: dict[str, Any], from_cache: bool = False) -> None:
        for field, expected in EXPECTED_RUNTIME.items():
            actual = runtime.get(field)
            if actual != expected:
                origin = "cache hit" if from_cache else "response"
                raise RuntimeError(
                    f"Runtime drift on {origin}: {field}={actual!r}, expected {expected!r}"
                )
        fingerprint = runtime.get("system_fingerprint") or runtime.get("model_version")
        if not fingerprint:
            raise RuntimeError("Runtime provenance missing system_fingerprint/model_version")
        with self._lock:
            if self.fingerprint is None:
                self.fingerprint = str(fingerprint)
            elif str(fingerprint) != self.fingerprint:
                raise RuntimeError(
                    f"Runtime fingerprint drift: {fingerprint!r} vs namespace fingerprint {self.fingerprint!r}"
                )

    def validate_record(self, rec: dict[str, Any], from_cache: bool = False) -> None:
        self.validate_runtime(rec.get("runtime", {}), from_cache=from_cache)
        if rec.get("parse_error"):
            raise RuntimeError(
                f"Refusing cached parse failure for {rec.get('uid')}/{rec.get('arm')}: {rec.get('parse_error')}"
            )
        if "answer" not in rec:
            raise RuntimeError(f"Cached record missing parsed answer for {rec.get('uid')}/{rec.get('arm')}")

    def write_error(self, key: str, uid: str, arm: str, attempt: int, response: dict[str, Any], parse_error: str) -> None:
        error_path = self.path + ".errors"
        rec = {
            "key": key,
            "uid": uid,
            "arm": arm,
            "attempt": attempt,
            "raw_response": response.get("text", ""),
            "parse_error": parse_error,
            "runtime": response.get("runtime", {}),
        }
        with open(error_path, "a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def call(self, key: str, uid: str, arm: str, messages: list[dict], dry_run: bool) -> tuple[dict, bool]:
        if key in self.data:
            self.validate_record(self.data[key], from_cache=True)
            return self.data[key], True
        if dry_run:
            raise RuntimeError(f"Missing cache: {uid}/{arm}")
        last_parse_error = None
        response = {}
        answer = None
        parse_error = None
        for attempt in range(PARSE_MAX_RETRIES):
            response = llm.call_once_with_metadata(
                messages,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                timeout=240,
                response_format=RESPONSE_FORMAT,
            )
            self.validate_runtime(response.get("runtime", {}), from_cache=False)
            answer, parse_error = parse_answer(response["text"])
            if parse_error is None:
                break
            last_parse_error = parse_error
            self.write_error(key, uid, arm, attempt + 1, response, parse_error)
        if parse_error is not None:
            raise RuntimeError(
                f"LLM response for {uid}/{arm} failed JSON parsing after {PARSE_MAX_RETRIES} attempts: "
                f"{last_parse_error}"
            )
        rec = {
            "key": key,
            "uid": uid,
            "arm": arm,
            "raw_response": response["text"],
            "answer": answer,
            "parse_error": parse_error,
            "runtime": response.get("runtime", {}),
        }
        with open(self.path, "a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        with self._lock:
            self.data[key] = rec
        return rec, False


def cache_key(uid: str, arm: str, prompt: str, case_ids: list[str], strategy_ids: list[str]) -> str:
    return stable_hash({
        "version": VERSION,
        "uid": uid,
        "arm": arm,
        "runtime": llm.runtime_config(),
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "thinking": False,
        "response_format": RESPONSE_FORMAT,
        "case_ids": case_ids,
        "strategy_ids": strategy_ids,
        "system": SYSTEM,
        "prompt": prompt,
    })


# ── Sample + retrieval ────────────────────────────────────────────────────────

def select_sample(val_rows: list[dict[str, Any]], sample_n: int) -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    indexed = list(enumerate(val_rows))
    full = rng.sample(indexed, FULL_SAMPLE_N)
    return [row for _, row in full[:sample_n]]


def source_id(row: dict[str, Any]) -> str:
    """Re-derive source hash used in case memory exclusion."""
    import hashlib as _hl, json as _j
    payload = _j.dumps(
        {"paragraphs": row.get("paragraphs") or [], "tables": row.get("tables") or []},
        sort_keys=True, ensure_ascii=False,
    )
    return _hl.md5(payload.encode("utf-8")).hexdigest()


def prepare_retrieval(
    sample: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    strategies: list[dict[str, Any]],
    strategy_emb: np.ndarray,
) -> dict[str, Any]:
    cases_by_id = {c["case_id"]: c for c in cases}
    prep = {}
    for row in sample:
        uid = row["uid"]
        src = source_id(row)

        # Case: full-context query, source exclusion
        case_query = make_target_retrieval_text(row)
        case_hits = retrieve_cases(case_query, k=CASE_TOP_K, exclude_source_id=src)
        case_blocks = [
            short_case_block(cases_by_id[h["case_id"]], h["score"])
            for h in case_hits
            if h["case_id"] in cases_by_id
        ]

        # Strategy: question-only + family-dedup (Stage 32 protocol)
        strategy_hits = retrieve_strategies_qonly_dedup(
            row["question"], strategies, strategy_emb,
            k_expand=STRATEGY_TOP_K_EXPAND, top_n=3,
        )
        strategy_blocks = [
            short_strategy_block(next(s for s in strategies if s["strategy_id"] == h["strategy_id"]), h["score"])
            for h in strategy_hits
        ]

        # Gold family for retrieval-conditioned analysis
        absr = abstract_record(row, 0)
        gold_family = absr.get("family", "")
        gold_type = strategy_type_label(absr)
        family_hit = any(h["family"] == gold_family for h in strategy_hits)

        prep[uid] = {
            "case_hits": [{"case_id": h["case_id"], "score": h["score"]} for h in case_hits],
            "strategy_hits": strategy_hits,
            "case_blocks": case_blocks,
            "strategy_blocks": strategy_blocks,
            "gold_family": gold_family,
            "gold_type": gold_type,
            "family_hit": family_hit,
        }
    return prep


# ── Evaluation ────────────────────────────────────────────────────────────────

def run(dry_run: bool = False, sample_n: int = DEFAULT_SAMPLE_N, cache_suffix: str = "") -> dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True)
    val_rows = load_rows("validation")
    sample = select_sample(val_rows, sample_n)
    paths = artifact_paths(cache_suffix)

    print(f"Loading memory and embeddings…")
    cases = load_json(CASE_MEMORY_PATH)
    strategies = load_json(STRATEGY_MEMORY_PATH)
    strategy_emb = embed_strategies(strategies)

    print(f"Preparing retrieval for {len(sample)} samples…")
    retrieval = prepare_retrieval(sample, cases, strategies, strategy_emb)

    cache = ExecCache(paths["cache"])
    outputs: dict[str, dict[str, dict[str, Any]]] = {arm: {} for arm in ARMS}

    tasks = []
    for row in sample:
        uid = row["uid"]
        r = retrieval[uid]
        for arm in ARMS:
            prompt = build_prompt(row, arm, r["case_blocks"], r["strategy_blocks"])
            key = cache_key(uid, arm, prompt, [h["case_id"] for h in r["case_hits"]], [h["strategy_id"] for h in r["strategy_hits"]])
            messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
            tasks.append((key, uid, arm, messages))

    api_calls = 0
    cache_hits = 0
    print(f"Executing {len(tasks)} arm×sample calls (concurrency={CONCURRENCY})…")
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futs = {
            ex.submit(cache.call, key, uid, arm, msgs, dry_run): (uid, arm)
            for key, uid, arm, msgs in tasks
        }
        for fut in as_completed(futs):
            uid, arm = futs[fut]
            rec, hit = fut.result()
            outputs[arm][uid] = rec
            cache_hits += int(hit)
            api_calls += int(not hit)

    # ── Evaluate ──────────────────────────────────────────────────────────────
    print("Evaluating…")
    arm_evals: dict[str, dict[str, Any]] = {}
    arm_details: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        preds = {uid: {"predicted_ans": out["answer"]} for uid, out in outputs[arm].items()}
        result = evaluate_rows(sample, preds)
        arm_evals[arm] = result
        arm_details[arm] = {d["uid"]: d for d in result["details"]}

    # Per-sample correctness
    correctness: dict[str, dict[str, dict[str, float]]] = {}
    for row in sample:
        uid = row["uid"]
        correctness[uid] = {
            arm: {"em": float(arm_details[arm][uid]["em"]), "f1": float(arm_details[arm][uid]["f1"])}
            for arm in ARMS
        }

    oracle_em = float(np.mean([
        max(correctness[row["uid"]][a]["em"] for a in ARMS) for row in sample
    ]))
    best_fixed = max(ARMS, key=lambda a: arm_evals[a]["exact_match"])

    # ── Retrieval-conditioned analysis ────────────────────────────────────────
    hit_uids = [uid for uid, r in retrieval.items() if r["family_hit"]]
    miss_uids = [uid for uid, r in retrieval.items() if not r["family_hit"]]

    def mean_em(arm: str, uids: list[str]) -> float:
        if not uids:
            return float("nan")
        return float(np.mean([correctness[uid][arm]["em"] for uid in uids]))

    retrieval_conditioned = {
        "family_hit_n": len(hit_uids),
        "family_miss_n": len(miss_uids),
        "hit": {arm: mean_em(arm, hit_uids) for arm in ARMS},
        "miss": {arm: mean_em(arm, miss_uids) for arm in ARMS},
        "overall": {arm: arm_evals[arm]["exact_match"] for arm in ARMS},
    }

    # ── Contingency ───────────────────────────────────────────────────────────
    arm_correct = {
        arm: {row["uid"] for row in sample if correctness[row["uid"]][arm]["em"] == 1.0}
        for arm in ARMS
    }
    event_counts = {
        "case_only": len(arm_correct["case"] - arm_correct["none"] - arm_correct["strategy"] - arm_correct["both"]),
        "strategy_only": len(arm_correct["strategy"] - arm_correct["none"] - arm_correct["case"] - arm_correct["both"]),
        "none_only": len(arm_correct["none"] - arm_correct["case"] - arm_correct["strategy"] - arm_correct["both"]),
        "both_only": len(arm_correct["both"] - arm_correct["none"] - arm_correct["case"] - arm_correct["strategy"]),
        "none_gt_both": sum(
            correctness[row["uid"]]["none"]["em"] > correctness[row["uid"]]["both"]["em"] for row in sample
        ),
        "case_gt_both": sum(
            correctness[row["uid"]]["case"]["em"] > correctness[row["uid"]]["both"]["em"] for row in sample
        ),
        "strategy_gt_both": sum(
            correctness[row["uid"]]["strategy"]["em"] > correctness[row["uid"]]["both"]["em"] for row in sample
        ),
    }

    # ── Per-type (program / span) ──────────────────────────────────────────────
    program_uids = [row["uid"] for row in sample if (row.get("program") or "").strip()]
    span_uids = [row["uid"] for row in sample if not (row.get("program") or "").strip()]
    by_answer_type = {
        "program": {arm: mean_em(arm, program_uids) for arm in ARMS},
        "span": {arm: mean_em(arm, span_uids) for arm in ARMS},
    }

    # ── Per-sample records ────────────────────────────────────────────────────
    records = []
    for row in sample:
        uid = row["uid"]
        r = retrieval[uid]
        records.append({
            "uid": uid,
            "question": row.get("question", ""),
            "answer_type": "program" if (row.get("program") or "").strip() else "span",
            "gold_answer": row.get("answer"),
            "gold_family": r["gold_family"],
            "gold_type": r["gold_type"],
            "family_hit": r["family_hit"],
            "strategy_hits": [{"strategy_id": h["strategy_id"], "family": h["family"], "score": h["score"]} for h in r["strategy_hits"]],
            "correct_arms": [arm for arm in ARMS if correctness[uid][arm]["em"] == 1.0],
            "em": {arm: correctness[uid][arm]["em"] for arm in ARMS},
            "predictions": {arm: outputs[arm][uid].get("answer") for arm in ARMS},
        })

    # ── Runtime normalization check ───────────────────────────────────────────
    runtime_check: Counter = Counter()
    parse_failures_by_arm: dict[str, int] = {}
    for arm_outputs in outputs.values():
        for out in arm_outputs.values():
            rt = out.get("runtime", {})
            runtime_check[rt.get("response_model") or "missing"] += 1
    for arm in ARMS:
        parse_failures_by_arm[arm] = sum(1 for out in outputs[arm].values() if out.get("parse_error"))

    audit = {
        "version": VERSION,
        "sample_n": len(sample),
        "seed": SEED,
        "sample_selection": f"first {sample_n} of fixed {FULL_SAMPLE_N}-sample validation set",
        "arms": ARMS,
        "case_top_k": CASE_TOP_K,
        "strategy_top_k": 3,
        "strategy_query_method": "question_only_family_dedup_k10",
        "execution_cache": os.path.relpath(paths["cache"], ROOT),
        "runtime_request": llm.runtime_config(),
        "observed_response_models": dict(runtime_check),
        "runtime_guard": {
            "expected": EXPECTED_RUNTIME,
            "namespace_fingerprint": cache.fingerprint,
        },
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "response_format": RESPONSE_FORMAT,
        "api_calls_made": api_calls,
        "cache_hits": cache_hits,
        "cache_records_after": len(cache.data),
        "diagnostic_parse_retry_records": count_jsonl(paths["cache"] + ".errors"),
        "arm_metrics": {
            arm: {
                "exact_match": arm_evals[arm]["exact_match"],
                "f1": arm_evals[arm]["f1"],
                "by_answer_type": arm_evals[arm]["by_answer_type"],
                "missing_predictions": arm_evals[arm]["missing_predictions"],
                "parse_failures": parse_failures_by_arm[arm],
            }
            for arm in ARMS
        },
        "best_fixed_arm": best_fixed,
        "best_fixed_em": arm_evals[best_fixed]["exact_match"],
        "oracle_em": oracle_em,
        "oracle_gap": oracle_em - arm_evals[best_fixed]["exact_match"],
        "retrieval_conditioned": retrieval_conditioned,
        "event_counts": event_counts,
        "by_answer_type": by_answer_type,
        "records": records,
        "decision": "FIX PIPELINE FIRST",
        "decision_rationale": (
            "Execution/cache/provenance layer is repaired, but absolute EM remains low "
            "and the 60-sample oracle gap is only 1/60; run context/prompt/evaluator audit "
            "before repeated-run expansion."
        ),
    }
    dump_json(paths["json"], audit)
    write_report(audit, paths["report"])

    summary = {
        "sample_n": len(sample),
        "api_calls_made": api_calls,
        "cache_hits": cache_hits,
        "arm_em": {a: arm_evals[a]["exact_match"] for a in ARMS},
        "best_fixed": best_fixed,
        "best_fixed_em": audit["best_fixed_em"],
        "oracle_em": oracle_em,
        "oracle_gap": audit["oracle_gap"],
        "retrieval_hit_n": retrieval_conditioned["family_hit_n"],
        "retrieval_miss_n": retrieval_conditioned["family_miss_n"],
        "strategy_em_on_hit": retrieval_conditioned["hit"]["strategy"],
        "strategy_em_on_miss": retrieval_conditioned["miss"]["strategy"],
        "none_em_on_hit": retrieval_conditioned["hit"]["none"],
        "none_em_on_miss": retrieval_conditioned["miss"]["none"],
        "event_counts": event_counts,
        "decision": audit["decision"],
        "report": os.path.relpath(paths["report"], ROOT),
    }
    print(json.dumps(summary, indent=2))
    return audit


def write_report(audit: dict[str, Any], report_path: str) -> None:
    arms = audit["arms"]
    em = audit["arm_metrics"]
    rc = audit["retrieval_conditioned"]
    ec = audit["event_counts"]

    def fmt(v: Any) -> str:
        if isinstance(v, float) and v != v:
            return "n/a"
        return f"{v:.3f}" if isinstance(v, float) else str(v)

    lines = [
        "# MultiHiertt Four-Arm Dry-Run — Stage 33",
        "",
        f"Date: 2026-08-18",
        "",
        "## Setup",
        "",
        f"- Sample: {audit['sample_selection']} (seed {audit['seed']}).",
        f"- Arms: {', '.join(arms)}.",
        f"- Case retrieval: full-context query, top-{audit['case_top_k']}, source_id exclusion.",
        f"- Strategy retrieval: question-only query + family-dedup top-3 from k={STRATEGY_TOP_K_EXPAND} (Stage 32 protocol).",
        f"- Runtime: `{audit['runtime_request']['backend']}` / `{audit['runtime_request']['requested_model']}`, temp={audit['temperature']}, max_tokens={audit['max_tokens']}.",
        f"- Observed response models: {audit['observed_response_models']}.",
        f"- Runtime guard: `{audit['runtime_guard']}`.",
        f"- Response format: `{audit['response_format']}`.",
        f"- Execution cache: `{audit['execution_cache']}`.",
        f"- API calls={audit['api_calls_made']}; cache hits={audit['cache_hits']}.",
        f"- Diagnostic parse retry records: {audit['diagnostic_parse_retry_records']} (not counted as successful cache records).",
        "",
        "## Four-Arm Metrics",
        "",
        "| Arm | EM | F1 | Parse failures |",
        "|---|---:|---:|---:|",
    ]
    for arm in arms:
        r = em[arm]
        lines.append(f"| `{arm}` | {fmt(r['exact_match'])} | {fmt(r['f1'])} | {r['parse_failures']} |")
    lines.extend([
        "",
        f"Best Fixed: `{audit['best_fixed_arm']}` EM={fmt(audit['best_fixed_em'])}.",
        f"Oracle EM={fmt(audit['oracle_em'])}.  Oracle Gap={fmt(audit['oracle_gap'])}.",
        "",
        "## Retrieval-Conditioned Analysis",
        "",
        f"- Strategy family hit (gold family in top-3 dedup): {rc['family_hit_n']}/{rc['family_hit_n'] + rc['family_miss_n']}",
        "",
        "| Arm | EM on hit | EM on miss | EM overall |",
        "|---|---:|---:|---:|",
    ])
    for arm in arms:
        lines.append(
            f"| `{arm}` | {fmt(rc['hit'][arm])} | {fmt(rc['miss'][arm])} | {fmt(rc['overall'][arm])} |"
        )
    lines.extend([
        "",
        "Interpretation guideline:",
        "- Strategy EM on hit > None EM on hit → strategy helps when retrieved correctly.",
        "- Strategy EM on miss < None EM on miss → strategy causes interference when retrieval fails.",
        "",
        "## Memory Effect Events",
        "",
    ])
    for k, v in ec.items():
        lines.append(f"- `{k}`: {v}")
    lines.extend([
        "",
        "## By Answer Type",
        "",
        "| Type | N | none EM | case EM | strategy EM | both EM |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    records = audit["records"]
    prog_n = sum(1 for r in records if r["answer_type"] == "program")
    span_n = sum(1 for r in records if r["answer_type"] == "span")
    bat = audit["by_answer_type"]
    lines.append(f"| program | {prog_n} | {fmt(bat['program']['none'])} | {fmt(bat['program']['case'])} | {fmt(bat['program']['strategy'])} | {fmt(bat['program']['both'])} |")
    lines.append(f"| span    | {span_n} | {fmt(bat['span']['none'])} | {fmt(bat['span']['case'])} | {fmt(bat['span']['strategy'])} | {fmt(bat['span']['both'])} |")
    lines.extend([
        "",
        "## Sample Records (interesting: not all-correct or all-wrong)",
        "",
    ])
    interesting = [r for r in records if len(r["correct_arms"]) not in {0, 4}][:10]
    if not interesting:
        interesting = records[:6]
    for r in interesting:
        lines.append(
            f"- uid={r['uid']} type={r['answer_type']} gold={r['gold_family']} "
            f"hit={r['family_hit']} correct={r['correct_arms']} "
            f"Q: {r['question'][:120]}"
        )
        lines.append(f"  preds: {r['predictions']}")
    lines.extend([
        "",
        "## Decision",
        "",
        f"`{audit['decision']}`",
        "",
        audit["decision_rationale"],
    ])
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sample-n", type=int, default=DEFAULT_SAMPLE_N)
    parser.add_argument("--cache-suffix", default="")
    args = parser.parse_args()
    run(dry_run=args.dry_run, sample_n=args.sample_n, cache_suffix=args.cache_suffix)
