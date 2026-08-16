"""简单稳定的 retrieval：bge-small-en 稠密检索（决策：pilot 用单模型 baseline，不做复杂 retriever）。"""
import json, os, numpy as np
from sentence_transformers import SentenceTransformer
import config

_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(config.EMBED_MODEL, device=config.EMBED_DEVICE)
    return _model

def _path(name):
    return os.path.join(config.OUT_DIR, name)

def build_case_index():
    cases = json.load(open(_path("case_memory.json")))
    model = get_model()
    texts = [c["retrieval_text"] for c in cases]
    emb = model.encode(texts, batch_size=256, show_progress_bar=True, normalize_embeddings=True)
    np.save(_path("case_emb.npy"), emb)
    # 保存 id 顺序
    json.dump([c["case_id"] for c in cases], open(_path("case_order.json"), "w"))
    print("case index built:", emb.shape)

def load_case_index():
    emb = np.load(_path("case_emb.npy"))
    order = json.load(open(_path("case_order.json")))
    return emb, order

def retrieve_cases(query_text, k=None, exclude_report=None, exclude_company=None):
    k = k or config.TOP_K_CASE
    emb, order = load_case_index()
    model = get_model()
    q = model.encode([query_text], normalize_embeddings=True)[0]
    sims = emb @ q
    idx = np.argsort(-sims)
    out = []
    for i in idx:
        cid = order[int(i)]
        if exclude_report and cid.startswith(exclude_report):
            continue
        if exclude_company and cid.split("/")[0] == exclude_company:
            continue
        out.append({"case_id": cid, "score": float(sims[i])})
        if len(out) >= k:
            break
    return out

def build_strategy_index(strategies):
    model = get_model()
    texts = [s["retrieval_text"] for s in strategies]
    emb = model.encode(texts, batch_size=128, show_progress_bar=True, normalize_embeddings=True)
    np.save(_path("strategy_emb.npy"), emb)
    json.dump([s["strategy_id"] for s in strategies], open(_path("strategy_order.json"), "w"))
    print("strategy index built:", emb.shape)

def load_strategy_index():
    emb = np.load(_path("strategy_emb.npy"))
    order = json.load(open(_path("strategy_order.json")))
    return emb, order

def retrieve_strategies(query_text, k=None):
    k = k or config.TOP_K_STRATEGY
    emb, order = load_strategy_index()
    model = get_model()
    q = model.encode([query_text], normalize_embeddings=True)[0]
    sims = emb @ q
    idx = np.argsort(-sims)[:k]
    return [{"strategy_id": order[int(i)], "score": float(sims[int(i)])} for i in idx]

# ---- case-anchored strategy retrieval (v2, adopted) ----
# 决策：用 case 检索（同 struct 命中 63.6%）的 top-N cases 的 struct 来缩小策略候选，
# 再按 case 共现次数 + embedding 排序。family-hit@3 从 37.8% -> 64.3%。
_case_mem = None
_strat_meta = None

def _load_meta():
    global _case_mem, _strat_meta
    if _case_mem is None:
        cases = json.load(open(os.path.join(config.OUT_DIR, "case_memory.json")))
        _case_mem = {c["case_id"]: tuple(c["struct"]) for c in cases}
        _strat_meta = {}
        for s in json.load(open(os.path.join(config.OUT_DIR, "strategies_clean.json"))):
            _strat_meta[s["strategy_id"]] = [tuple(f) for f in s["program_family"]]
    return _case_mem, _strat_meta

def retrieve_strategies_v2(query_text, k=None, top_cases=8, exclude_company=None):
    k = k or config.TOP_K_STRATEGY
    case_struct, strat_fam = _load_meta()
    rc = retrieve_cases(query_text, top_cases, exclude_company=exclude_company)
    strat_ids = list(strat_fam.keys())
    cand = {}
    for r in rc:
        st = case_struct.get(r["case_id"])
        if st is None:
            continue
        for sid in strat_ids:
            if st in strat_fam[sid]:
                cand[sid] = cand.get(sid, 0) + 1
    if not cand:
        cand = {sid: 1 for sid in strat_ids}
    emb, order = load_strategy_index()
    model = get_model()
    q = model.encode([query_text], normalize_embeddings=True)[0]
    cand_ids = list(cand.keys())
    idx = [order.index(sid) for sid in cand_ids]
    sims = emb[idx] @ q
    rank = sorted(range(len(cand_ids)), key=lambda i: (-cand[cand_ids[i]], -sims[i]))
    return [{"strategy_id": cand_ids[i], "score": float(sims[i]), "case_hits": cand[cand_ids[i]]} for i in rank[:k]]

if __name__ == "__main__":
    build_case_index()
