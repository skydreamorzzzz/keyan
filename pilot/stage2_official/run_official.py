"""official-aligned 运行器：移植官方 FinQA pipeline（free-form）+ Experience Memory 扩展。
指标：reproduction（官方 Corrected exact/close, gold=qa.answer）；unified（FinQA exec, program）。
"""
import json, os, sys, hashlib
from concurrent.futures import ThreadPoolExecutor
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import s2o_common as c
import retrieval as pilot_retrieval
import config as pilot_config
import llm as pilot_llm

N = 492
K_FACTS = 12
TOP_CASE = 4
TOP_STRATEGY = 3
CACHE_KEY_VERSION = "stage2_official_full_prompt_v3_runtime_identity"

SYS_PROGRAM = (
    "You are solving a financial reasoning question (FinQA). Given the context and question, produce the "
    "numerical reasoning PROGRAM that computes the answer.\n\n"
    "Operations: add, subtract, multiply, divide, exp, greater, table_max, table_min, table_sum, table_average.\n"
    "- Arithmetic ops take two operands, each a number or a nested sub-expression.\n"
    "- table_* take a TABLE ROW LABEL as first arg and 'none' as second.\n"
    "- Numbers may carry units: '22%' for percent; const_1000/const_1000000/const_100/const_2/const_3 as needed.\n"
    "- Table cells may have noise: '-36 ( 36 )' means -36; '$ 1697.6' means 1697.6.\n"
    "- Facts may look like 'entity | column = value'; the operand is the VALUE after '='.\n"
    "- Use exact operator names; 'greater' not 'compare'.\n\n"
    "Output the program as a SINGLE nested expression, one line, no explanation. "
    "Example: divide(subtract(1697.6, 1739.5), 1739.5)"
)

def exp_block(case_blocks, strat_blocks):
    s = ""
    if case_blocks:
        s += "\n\nSIMILAR SOLVED CASES (reference for value extraction/structure; do NOT copy their numbers):\n" + "\n".join(case_blocks)
    if strat_blocks:
        s += "\n\nRELEVANT REASONING STRATEGIES (follow the one that applies):\n" + "\n".join(strat_blocks)
    return s

def structured_prompt_with_exp(facts, q, exp):
    base = c.build_prompt_structured(facts, q)
    if exp:
        base = base.replace("\nQuestion:\n", exp + "\nQuestion:\n", 1)
    return base

def stable_cache_key(mode, arm, sample_index, prompt, system):
    payload = {
        "version": CACHE_KEY_VERSION,
        "mode": mode,
        "arm": arm,
        "sample_index": sample_index,
        "runtime": pilot_llm.runtime_config(),
        "model": pilot_config.LLM_MODEL,
        "temperature": pilot_config.LLM_TEMPERATURE,
        "max_tokens": 600,
        "thinking_mode": False,
        "retrieval_config": {
            "k_facts": K_FACTS,
            "case_top_k": TOP_CASE,
            "strategy_top_k": TOP_STRATEGY,
            "embed_model": c.EMBED_MODEL,
            "case_retriever": "pilot_retrieval.retrieve_cases",
            "strategy_retriever": "pilot_retrieval.retrieve_strategies_v2",
        },
        "memory_config": {
            "case_memory": "pilot/output/case_memory.json",
            "strategy_memory": "pilot/output/strategies_clean.json",
            "case_facts_used": 3,
        },
        "system": system,
        "prompt": prompt,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()

def main():
    smoke = int(os.environ.get("SMOKE", "0"))
    dev = json.load(open(os.path.join(c.DATA, "dev.json")))
    ds = dev[:N]
    if smoke:
        ds = ds[:smoke]
    print(f"official-aligned sample: first {len(ds)} of dev")

    case_mem = {x["case_id"]: x for x in json.load(open(os.path.join(os.path.dirname(__file__), "..", "output", "case_memory.json")))}
    strat_by_id = {s["strategy_id"]: s for s in json.load(open(os.path.join(os.path.dirname(__file__), "..", "output", "strategies_clean.json")))}
    pilot_retrieval._load_meta()

    os.makedirs(c.OUT, exist_ok=True)
    out_path = os.path.join(c.OUT, "arm_outputs.json")
    results = json.load(open(out_path)) if os.path.exists(out_path) else {}
    cache_path = os.path.join(c.OUT, "llm_cache.jsonl")
    cached = {}
    if os.path.exists(cache_path):
        for line in open(cache_path):
            try:
                r = json.loads(line)
                cached[r["key"]] = r["out"]
            except Exception:
                pass

    def call(key, prompt, system):
        if key in cached:
            return cached[key]
        out = c.ask_llm(prompt, system=system)
        cached[key] = out
        with open(cache_path, "a") as f:
            f.write(json.dumps({"key": key, "out": out}, ensure_ascii=False) + "\n")
        return out

    # ---- precompute per-sample grounding + experience ----
    prep = {}
    for i, ex in enumerate(ds):
        context, question, gold = c.finqa_normalize(ex)
        qe = c.embed_texts([question])[0]
        rag_facts = c.build_facts_rag(ex)
        rag_emb = c.embed_texts(rag_facts)
        rag_top = [rag_facts[j] for j in np.argsort(-(rag_emb @ qe))[:K_FACTS]]
        struct_facts = c.table_to_facts_structured(ex.get("table")) + c.model_input_to_facts(ex.get("qa", {}).get("model_input"))
        se = c.embed_texts(struct_facts)
        top50 = [struct_facts[j] for j in np.argsort(-(se @ qe))[:50]]
        top50 = c.keyword_filter_facts(top50, question)
        top50 = c.drop_composite_row_facts(top50)
        struct_top = top50[:K_FACTS]
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
        prep[i] = {"context": context, "question": question, "gold": gold, "ex": ex,
                   "rag_top": rag_top, "struct_top": struct_top,
                   "case_blocks": case_blocks, "strat_blocks": strat_blocks}

    # ---- arm -> (prompt_fn(p), system) ----
    ff = {}
    for name, exp in [("baseline", None), ("baseline_case", "case"), ("baseline_strategy", "strategy"), ("baseline_both", "both")]:
        def fn(p, exp=exp, name=name):
            e = exp_block(p["case_blocks"], p["strat_blocks"]) if exp == "both" else (exp_block(p["case_blocks"], None) if exp == "case" else (exp_block(None, p["strat_blocks"]) if exp == "strategy" else ""))
            return c.build_prompt_baseline(p["context"] + e, p["question"]), c.FIN_SYSTEM
        ff[name] = fn
    for name, exp in [("structured", None), ("structured_case", "case"), ("structured_strategy", "strategy"), ("structured_both", "both")]:
        def fn(p, exp=exp):
            e = exp_block(p["case_blocks"], p["strat_blocks"]) if exp == "both" else (exp_block(p["case_blocks"], None) if exp == "case" else (exp_block(None, p["strat_blocks"]) if exp == "strategy" else ""))
            return structured_prompt_with_exp(p["struct_top"], p["question"], e), c.FIN_SYSTEM_STRUCTURED
        ff[name] = fn
    ff["rag"] = lambda p: (c.build_prompt_rag(p["rag_top"], p["question"]), c.FIN_SYSTEM)

    prog = {}
    for name, exp in [("baseline", None), ("baseline_case", "case"), ("baseline_strategy", "strategy"), ("baseline_both", "both")]:
        def fn(p, exp=exp):
            e = exp_block(p["case_blocks"], p["strat_blocks"]) if exp == "both" else (exp_block(p["case_blocks"], None) if exp == "case" else (exp_block(None, p["strat_blocks"]) if exp == "strategy" else ""))
            return "CONTEXT:\n" + p["context"] + e + f"\n\nQUESTION:\n{p['question']}\n\nPROGRAM:", SYS_PROGRAM
        prog[name] = fn
    for name, exp in [("structured", None), ("structured_case", "case"), ("structured_strategy", "strategy"), ("structured_both", "both")]:
        def fn(p, exp=exp):
            e = exp_block(p["case_blocks"], p["strat_blocks"]) if exp == "both" else (exp_block(p["case_blocks"], None) if exp == "case" else (exp_block(None, p["strat_blocks"]) if exp == "strategy" else ""))
            return "CONTEXT (facts):\n" + "\n".join(f"- {f}" for f in p["struct_top"]) + e + f"\n\nQUESTION:\n{p['question']}\n\nPROGRAM:", SYS_PROGRAM
        prog[name] = fn

    results.setdefault("ff", {})
    results.setdefault("prog", {})
    pending = []
    for i in prep:
        for mode, arms in [("ff", ff), ("prog", prog)]:
            for name, fn in arms.items():
                results[mode].setdefault(name, {})
                if str(i) not in results[mode][name]:
                    pending.append((i, mode, name, fn, prep[i]))
    print(f"pending arm-mode calls: {len(pending)}")

    def work(item):
        i, mode, name, fn, p = item
        prompt, sysp = fn(p)
        key = stable_cache_key(mode, name, i, prompt, sysp)
        return mode, name, i, call(key, prompt, sysp)

    failed = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for j, (mode, name, i, out) in enumerate(ex.map(work, pending), 1):
            if out is None:
                failed.append((mode, name, i))
                continue
            results[mode][name][i] = out
            if j % 30 == 0:
                json.dump(results, open(out_path, "w"), ensure_ascii=False)
                print(f"  {j}/{len(pending)} done")
    json.dump(results, open(out_path, "w"), ensure_ascii=False)
    if failed:
        print(f"[warn] failed={len(failed)}")

    # ---- mem0aug：顺序共享池（官方：同一 user_id 跨样本累积 context + Q/A）----
    results["ff"].setdefault("mem0aug", {})
    pool_texts, pool_emb_rows = [], []
    for i in sorted(prep.keys()):
        if i in results["ff"]["mem0aug"]:
            continue
        p = prep[i]
        if pool_emb_rows:
            pe = np.stack(pool_emb_rows)
            sims = pe @ c.embed_texts([p["question"]])[0]
            idx = np.argsort(-sims)[:40]
            remembered = "\n".join(f"- {pool_texts[j]}" for j in idx) if idx.size else "(none)"
        else:
            remembered = "(none)"
        prompt = c.build_prompt_mem0aug(remembered, p["context"], p["question"])
        key = stable_cache_key("ff", "mem0aug", i, prompt, c.FIN_SYSTEM)
        out = call(key, prompt, c.FIN_SYSTEM)
        results["ff"]["mem0aug"][str(i)] = out
        # 累积：context + Q/A（新项只 embed 一次）
        for t in (p["context"], f"Q: {p['question']}\nA: {out}"):
            pool_texts.append(t)
            pool_emb_rows.append(c.embed_texts([t])[0])
        json.dump(results, open(out_path, "w"), ensure_ascii=False)
        if i % 20 == 0:
            print(f"  mem0aug {i}/{len(prep)} done")

    json.dump(results, open(out_path, "w"), ensure_ascii=False)
    print(f"done. saved {out_path}")
    for mode in ["ff", "prog"]:
        for name in results.get(mode, {}):
            print(f"  {mode}/{name}: {len(results[mode][name])}")

if __name__ == "__main__":
    main()
