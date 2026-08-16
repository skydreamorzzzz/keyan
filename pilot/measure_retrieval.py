"""衡量 Strategy retrieval：baseline(纯 embedding) vs case-anchored 候选过滤。
输出 family-hit@k（program_family 包含 gold struct）。不做 dev 调参，只测量。"""
import json, os, numpy as np, collections
import config
import finqa_common as fc
from retrieval import (load_strategy_index, retrieve_strategies, retrieve_cases,
                       get_model, load_case_index)

def main():
    sample = json.load(open(os.path.join(config.OUT_DIR, "dev_sample.json")))
    dev = {x["id"]: x for x in json.load(open(os.path.join(config.DATA_DIR, "dev.json")))}
    cases = json.load(open(os.path.join(config.OUT_DIR, "case_memory.json")))
    case_struct = {c["case_id"]: tuple(c["struct"]) for c in cases}
    strategies = json.load(open(os.path.join(config.OUT_DIR, "strategies_clean.json")))
    strat_by_id = {s["strategy_id"]: s for s in strategies}
    strat_fam = {s["strategy_id"]: [tuple(f) for f in s["program_family"]] for s in strategies}
    strat_ids = [s["strategy_id"] for s in strategies]
    emb, _ = load_strategy_index()

    model = get_model()

    def family_hit(sids, gold_struct):
        return any(gold_struct in strat_fam[sid] for sid in sids)

    def retrieve_v2(query, k=3, top_cases=8):
        """case-anchored: 用 top cases 的 struct 缩小候选，再按 embedding 排序。"""
        rc = retrieve_cases(query, top_cases)
        cand = collections.Counter()
        for r in rc:
            st = case_struct.get(r["case_id"])
            if st is None:
                continue
            for sid in strat_ids:
                if st in strat_fam[sid]:
                    cand[sid] += 1
        # 至少保底：若候选为空，用全部策略
        if not cand:
            cand = collections.Counter({sid: 1 for sid in strat_ids})
        # 排序：先按出现次数（多案例共同指向），再按 embedding
        q = model.encode([query], normalize_embeddings=True)[0]
        cand_ids = list(cand.keys())
        idx = [strat_ids.index(sid) for sid in cand_ids]
        sims = emb[idx] @ q
        order = sorted(range(len(cand_ids)), key=lambda i: (-cand[cand_ids[i]], -sims[i]))
        return [cand_ids[i] for i in order[:k]]

    base_hit, v2_hit = {1:0,2:0,3:0}, {1:0,2:0,3:0}
    n = 0
    for qid in sample["ids"]:
        q = dev[qid]["qa"]["question"]
        gold_struct = tuple(sample["cat"][qid]["struct"])
        n += 1
        for k in (1,2,3):
            bs = retrieve_strategies(q, k)
            base_hit[k] += family_hit([r["strategy_id"] for r in bs], gold_struct)
            v2 = retrieve_v2(q, k)
            v2_hit[k] += family_hit(v2, gold_struct)

    print(f"n={n}")
    for k in (1,2,3):
        print(f"  family-hit@{k}: baseline={100*base_hit[k]/n:.1f}%  case-anchored={100*v2_hit[k]/n:.1f}%")

if __name__ == "__main__":
    main()
