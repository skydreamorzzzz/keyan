"""Stage 2 统一实验运行：reproduction（free-form）+ unified（program）双指标，多臂。
缓存可恢复。"""
import json, os, sys, hashlib
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import s2config as config
import finqa_common as fc
from s2_facts import doc_to_rag_facts, table_to_structured_facts, composite_filter
from s2_retrieval import retrieve_facts
from s2_prompts import build_prompt, make_context
from llm import CachedLLM
import retrieval as pilot_retrieval  # pilot 的跨样本检索（case/strategy）

def main():
    smoke = int(os.environ.get("SMOKE", "0"))
    dev = json.load(open(os.path.join(config.DATA, "dev.json")))
    rng = __import__("random").Random(config.SAMPLE_SEED)
    pool = [x["id"] for x in dev]
    rng.shuffle(pool)
    ids = pool[:config.SAMPLE_N]
    if smoke:
        ids = ids[:smoke]
    print(f"sample: {len(ids)} dev ids (seed {config.SAMPLE_SEED})")

    # 经验记忆池（pilot 产物）
    case_mem = {c["case_id"]: c for c in json.load(open(os.path.join(config.PILOT, "output", "case_memory.json")))}
    strat_by_id = {s["strategy_id"]: s for s in json.load(open(os.path.join(config.PILOT, "output", "strategies_clean.json")))}
    pilot_retrieval._load_meta()

    llm = CachedLLM(os.path.join(config.OUT, "cache.jsonl"))
    out_path = os.path.join(config.OUT, "arm_outputs.json")
    os.makedirs(config.OUT, exist_ok=True)
    results = json.load(open(out_path)) if os.path.exists(out_path) else {}

    dev_by_id = {x["id"]: x for x in dev}

    # 预计算每样本的 facts + retrieval（一次，供所有臂复用）
    prep = {}
    for qid in ids:
        x = dev_by_id[qid]
        q = x["qa"]["question"]
        table = x["table"]
        rag_all = doc_to_rag_facts(x["pre_text"], x["post_text"], table)
        struct_all = composite_filter(table_to_structured_facts(table))
        rag_top = retrieve_facts(q, rag_all, config.RETRIEVAL_K)
        struct_top = retrieve_facts(q, struct_all, config.RETRIEVAL_K)
        # 经验记忆
        rc = pilot_retrieval.retrieve_cases(q, config.TOP_CASE)
        rs = pilot_retrieval.retrieve_strategies_v2(q, config.TOP_STRATEGY)
        case_blocks = []
        for r in rc:
            c = case_mem[r["case_id"]]
            facts = " ; ".join(c["gold_facts"][:3])
            case_blocks.append(f"Case {c['case_id']}:\n  Question: {c['question']}\n  Facts: {facts}\n  Program: {c['program_re']}\n  Answer: {c['exe_ans']}")
        strat_blocks = []
        for r in rs:
            s = strat_by_id[r["strategy_id"]]
            strat_blocks.append(f"Strategy: {s['name']}\n  Pattern: {s['problem_pattern']}\n  Roles: {s['operand_roles']}\n  Procedure: {s['procedure']}\n  Formula: {s['formula']}\n  Template: {s['template']}\n  Scale: {s['canonical_output_scale']}\n  Units: {s['unit_convention']}")
        prep[qid] = {"q": q, "doc": x, "rag_facts": rag_top, "struct_facts": struct_top,
                     "case_blocks": case_blocks, "strat_blocks": strat_blocks}

    results.setdefault("repro", {})
    results.setdefault("unified", {})
    for grp, arms in [("repro", config.REPRO_ARMS), ("unified", config.UNIFIED_ARMS)]:
        for arm in arms:
            results[grp].setdefault(arm, {})

    pending = []
    for qid in ids:
        p = prep[qid]
        # reproduction arms (free-form)：baseline/rag/structured 并发；mem0aug 单独顺序
        for arm in ["baseline", "rag", "structured"]:
            if qid in results["repro"][arm]:
                continue
            ctx = make_context(arm, p["doc"], p)
            messages = build_prompt("freeform", p["q"], ctx)
            h = hashlib.sha1(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()[:10]
            key = f"repro|{arm}|{qid}|{h}"
            pending.append((key, messages, {"max_tokens": 300}, {"grp": "repro", "arm": arm, "qid": qid}))
        # unified arms (program)
        for arm in config.UNIFIED_ARMS:
            if qid in results["unified"][arm]:
                continue
            ctx = make_context(arm, p["doc"], p, case_blocks=p["case_blocks"], strategy_blocks=p["strat_blocks"])
            messages = build_prompt("program", p["q"], ctx)
            h = hashlib.sha1(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()[:10]
            key = f"unified|{arm}|{qid}|{h}"
            pending.append((key, messages, {"max_tokens": config.LLM_MAX_TOKENS}, {"grp": "unified", "arm": arm, "qid": qid}))

    print(f"pending calls: {len(pending)}")

    def work(item):
        key, messages, kw, meta = item
        try:
            return meta, llm.call(key, messages, **kw), None
        except Exception as e:
            return meta, None, str(e)

    failed = []
    with ThreadPoolExecutor(max_workers=config.LLM_CONCURRENCY) as ex:
        for i, (meta, raw, err) in enumerate(ex.map(work, pending), 1):
            if err is not None:
                failed.append((meta["arm"], meta["qid"], err))
                continue
            results[meta["grp"]][meta["arm"]][meta["qid"]] = raw
            if i % 30 == 0:
                json.dump(results, open(out_path, "w"), ensure_ascii=False)
                print(f"  {i}/{len(pending)} done")
    json.dump(results, open(out_path, "w"), ensure_ascii=False)
    if failed:
        print(f"[warn] {len(failed)} failed: {failed[:5]}")

    # mem0aug：顺序处理，累积共享记忆池（论文设计：persistent cross-session store）
    mem_pool = []
    for qid in ids:
        if qid in results["repro"]["mem0aug"]:
            continue
        p = prep[qid]
        mem_text = "\n".join(mem_pool[-40:]) if mem_pool else ""
        ctx = make_context("mem0aug", p["doc"], None, memory_text=mem_text)
        messages = build_prompt("freeform", p["q"], ctx)
        h = hashlib.sha1(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()[:10]
        key = f"repro|mem0aug|{qid}|{h}"
        raw = llm.call(key, messages, max_tokens=300)
        results["repro"]["mem0aug"][qid] = raw
        # 累积：完整文档 + 本样本 Q/A（论文：context addition + Q/A append）
        mem_pool.append(f"Q: {p['q']}\nA: {raw}")
        json.dump(results, open(out_path, "w"), ensure_ascii=False)
    print("mem0aug sequential pass done")

    print("done. saved", out_path)

    # 统计
    for grp in ["repro", "unified"]:
        for arm in results.get(grp, {}):
            print(f"  {grp}/{arm}: {len(results[grp][arm])}")

if __name__ == "__main__":
    main()
