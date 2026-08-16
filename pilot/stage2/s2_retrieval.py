"""当前文档内的事实检索（RAG / Structured 共用）。论文用 Ollama 的 nomic-embed-text + Python 余弦。
我们以 bge-small-en 替代（记录差异）。对每个文档的事实一次 embedding 并缓存。"""
import os, json
import numpy as np
from sentence_transformers import SentenceTransformer
import s2config as config

_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(config.EMBED_MODEL, device="cpu")
    return _model

def retrieve_facts(query, facts, k=None, model=None):
    """在给定文档的 facts 中检索 top-k。facts: list[dict{fact,...}]。"""
    k = k or config.RETRIEVAL_K
    model = model or get_model()
    texts = [f["fact"] for f in facts]
    if not texts:
        return []
    emb = model.encode(texts, batch_size=256, normalize_embeddings=True)
    q = model.encode([query], normalize_embeddings=True)[0]
    sims = emb @ q
    idx = np.argsort(-sims)[:k]
    out = []
    for i in idx:
        out.append({**facts[int(i)], "score": float(sims[int(i)])})
    return out
