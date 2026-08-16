"""运行 Clean Oracle 的 6 臂生成（双样本：stratified + natural）。可恢复。

Arms:
  no          : 无记忆
  case_all    : Case-All（原检索）
  case_cc     : Case-CrossCompany（检索排除同公司）
  strategy    : Strategy-Clean（case-anchored 检索 v2）
  both_all    : Case-All + Strategy
  both_cc     : Case-CrossCompany + Strategy
"""
import json, os, hashlib
from concurrent.futures import ThreadPoolExecutor
import config
import finqa_common as fc
import retrieval
from llm import CachedLLM
from prompts import build_prompt

ARMS = [
    ("no",          False, False, False),
    ("case_all",    True,  False, False),
    ("case_cc",     True,  False, True),
    ("strategy",    False, True,  False),
    ("both_all",    True,  True,  False),
    ("both_cc",     True,  True,  True),
]

def main():
    samples_env = os.environ.get("SAMPLES", "strat")
    if samples_env == "both":
        sample_files = ["dev_sample.json", "dev_sample_natural.json"]
    elif samples_env == "natural":
        sample_files = ["dev_sample_natural.json"]
    else:
        sample_files = ["dev_sample.json"]
    smoke = int(os.environ.get("SMOKE", "0"))

    dev = {x["id"]: x for x in json.load(open(os.path.join(config.DATA_DIR, "dev.json")))}
    cases = {c["case_id"]: c for c in json.load(open(os.path.join(config.OUT_DIR, "case_memory.json")))}
    strategies = {s["strategy_id"]: s for s in json.load(open(os.path.join(config.OUT_DIR, "strategies_clean.json")))}
    llm = CachedLLM(os.path.join(config.OUT_DIR, "arm_cache_clean.jsonl"))

    out_path = os.path.join(config.OUT_DIR, "arm_outputs_clean.json")
    results = {}
    if os.path.exists(out_path):
        results = json.load(open(out_path))

    for sf in sample_files:
        sample = json.load(open(os.path.join(config.OUT_DIR, sf)))
        tag = "nat" if "natural" in sf else "strat"
        ids = sample["ids"]
        if smoke:
            ids = ids[:smoke]
        print(f"[sample {tag}] {len(ids)} queries")
        results.setdefault(tag, {})
        for arm, use_case, use_strat, xcomp in ARMS:
            results[tag].setdefault(arm, {})

        pending = []
        for qid in ids:
            x = dev[qid]
            q = x["qa"]["question"]
            context = fc.format_context(x["pre_text"], x["post_text"], x["table"])
            company = fc.company_of(qid)
            # 每 query 显式计算两套 case 检索 + 一套 strategy 检索（锚定完整 case 池，不排除公司）
            rc_all = retrieval.retrieve_cases(q, config.TOP_K_CASE)
            rc_cc = retrieval.retrieve_cases(q, config.TOP_K_CASE, exclude_company=company)
            case_all_recs = [cases[r["case_id"]] for r in rc_all]
            case_cc_recs = [cases[r["case_id"]] for r in rc_cc]
            rs = retrieval.retrieve_strategies_v2(q, config.TOP_K_STRATEGY)
            strat_recs = [strategies[r["strategy_id"]] for r in rs]
            arm_mem = {
                "no":       (None, None),
                "case_all": (case_all_recs, None),
                "case_cc":  (case_cc_recs, None),
                "strategy": (None, strat_recs),
                "both_all": (case_all_recs, strat_recs),
                "both_cc":  (case_cc_recs, strat_recs),
            }
            for arm, use_case, use_strat, _ in ARMS:
                if qid in results[tag][arm]:
                    continue
                mem_cases, mem_strats = arm_mem[arm]
                messages = build_prompt(arm, q, context,
                                        cases=mem_cases, strategies=mem_strats)
                h = hashlib.sha1(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()[:10]
                key = f"{tag}|{arm}|{qid}|{h}"
                rc_for_record = rc_cc if arm in ("case_cc", "both_cc") else rc_all
                pending.append((key, messages, {"max_tokens": config.LLM_MAX_TOKENS}, {
                    "tag": tag, "arm": arm, "qid": qid,
                    "retrieved_cases": [{"id": r["case_id"], "score": r["score"]} for r in rc_for_record],
                    "retrieved_strategies": [{"id": r["strategy_id"], "score": r["score"]} for r in rs],
                }))

        print(f"pending calls: {len(pending)}")
        if not pending:
            continue

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
                results[meta["tag"]][meta["arm"]][meta["qid"]] = {
                    "raw": raw,
                    "retrieved_cases": meta["retrieved_cases"],
                    "retrieved_strategies": meta["retrieved_strategies"],
                }
                if i % 25 == 0:
                    json.dump(results, open(out_path, "w"), ensure_ascii=False)
                    print(f"  {i}/{len(pending)} done")
        json.dump(results, open(out_path, "w"), ensure_ascii=False)
        if failed:
            print(f"[warn] {len(failed)} failed: {failed[:5]}")

    print("done. saved", out_path)
    for tag in results:
        for arm in [a[0] for a in ARMS]:
            print(f"  {tag}/{arm}: {len(results[tag].get(arm, {}))}")

if __name__ == "__main__":
    main()
