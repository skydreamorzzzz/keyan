"""official-aligned 公共模块：从官方仓库 JLiu24-Eng/.../src/run_finqa_*.py 逐段移植。
替换：Ollama→DeepSeek API；nomic-embed→bge-small-en。其余实验逻辑保持官方一致。
gold 用 qa["answer"]；492 = dev 前 492 条。
"""
import json, math, os, re, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from llm import call_once
from sentence_transformers import SentenceTransformer

DATA = "/home/tiantian/keyan/data/finqa"
OUT = os.path.join(os.path.dirname(__file__), "output")
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

# ---------------- 官方 system prompts（逐字） ----------------
FIN_SYSTEM = (
    "You are a financial reasoning assistant. "
    "Answer the question using ONLY the given context. "
    "If calculation is required, do it carefully. "
    "Return ONLY the final answer (a number or short phrase)."
)
FIN_SYSTEM_STRUCTURED = (
    "You are a financial question answering assistant.\n"
    "Use ONLY the FACTS provided.\n"
    "You MAY derive values using standard arithmetic.\n"
    "Do NOT invent or assume new facts beyond the provided FACTS.\n"
    "Do NOT rescale numbers (e.g., do not turn 637 into 637,000,000).\n"
    "Do NOT convert units unless the question explicitly asks for conversion.\n"
    "If numerator and denominator share the same unit (e.g., both billions), the unit cancels; use raw numbers.\n"
    "Return ONLY the final numeric answer (optionally with %)."
)

# ---------------- LLM / embedding 客户端（替换 backbone/API） ----------------
def ask_llm(prompt, system=FIN_SYSTEM):
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    return call_once(messages, max_tokens=600)

_emb_model = None
def embed_texts(texts):
    global _emb_model
    if _emb_model is None:
        _emb_model = SentenceTransformer(EMBED_MODEL, device="cpu")
    return _emb_model.encode(texts, batch_size=256, normalize_embeddings=True)

def cosine_sim(q, facts_emb):
    return facts_emb @ q

# ---------------- finqa normalize（官方） ----------------
def finqa_normalize(ex):
    qa = ex.get("qa", {}) or {}
    question = (qa.get("question") or "").strip()
    answer = str(qa.get("answer") or "").strip()
    pre = ex.get("pre_text") or []
    post = ex.get("post_text") or []
    table = ex.get("table") or []
    pre_text = "\n".join([s.strip() for s in pre if isinstance(s, str) and s.strip()])
    post_text = "\n".join([s.strip() for s in post if isinstance(s, str) and s.strip()])
    table_str = ""
    if isinstance(table, list) and table:
        if isinstance(table[0], list):
            table_str = "\n".join(["\t".join([str(c) for c in row]) for row in table])
        else:
            table_str = str(table)
    parts = []
    if pre_text:
        parts.append("Pre-text:\n" + pre_text)
    if table_str:
        parts.append("Table:\n" + table_str)
    if post_text:
        parts.append("Post-text:\n" + post_text)
    context = "\n\n".join(parts).strip()
    return context, question, answer

# ---------------- RAG facts（官方 run_finqa_rag.py） ----------------
def normalize_text_lines(x, max_lines=120):
    if x is None:
        return []
    if isinstance(x, list):
        out = [str(t).strip() for t in x if str(t).strip()]
        return out[:max_lines]
    s = str(x).strip()
    return [s] if s else []

def table_to_facts_rag(table, max_rows=60):
    if not table or not isinstance(table, list) or len(table) < 2:
        return []
    header = [str(c).strip() for c in table[0]]
    facts = []
    for row in table[1:1 + max_rows]:
        if not isinstance(row, list):
            continue
        cells = [str(c).strip() for c in row]
        pairs = []
        for h, v in zip(header, cells):
            if h and v:
                pairs.append(f"{h}: {v}")
        if pairs:
            facts.append(" | ".join(pairs))
        else:
            joined = "\t".join(cells).strip()
            if joined:
                facts.append(joined)
    return facts

def build_facts_rag(ex, max_pre=60, max_post=60):
    pre = normalize_text_lines(ex.get("pre_text"), max_lines=max_pre)
    post = normalize_text_lines(ex.get("post_text"), max_lines=max_post)
    tfacts = table_to_facts_rag(ex.get("table"), max_rows=60)
    facts = [f"PRE: {s}" for s in pre] + [f"TABLE: {s}" for s in tfacts] + [f"POST: {s}" for s in post]
    seen, out = set(), []
    for f in facts:
        k = f.strip()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out

# ---------------- Structured facts（官方 run_finqa_structured_mem0.py） ----------------
def normalize_cell(s):
    return re.sub(r"\s+", " ", str(s).strip().lower())

def table_to_facts_structured(table, max_rows=25):
    if not table or not isinstance(table, list) or len(table) < 2:
        return []
    header = [normalize_cell(x) for x in table[0]]
    facts = []
    for row in table[1:1 + max_rows]:
        if not isinstance(row, list) or len(row) < 2:
            continue
        entity = normalize_cell(row[0])
        if not entity:
            continue
        for j in range(1, min(len(row), len(header))):
            col = header[j] if header[j] else f"col_{j}"
            val = str(row[j]).strip()
            if not val or val == ".":
                continue
            facts.append(f"{entity} | {col} = {val}")
    return facts

def model_input_to_facts(model_input):
    facts = []
    for item in model_input or []:
        if isinstance(item, list) and len(item) == 2:
            txt = str(item[1]).strip()
            if txt:
                facts.append(txt)
    return facts

# ---------------- filters（官方，逐字移植） ----------------
def drop_composite_row_facts(facts):
    if not facts:
        return facts
    atomic, composite = [], []
    for f in facts:
        fl = f.strip().lower()
        if (f.count(";") >= 2) or fl.startswith("company the "):
            composite.append(f)
        else:
            atomic.append(f)
    return atomic if atomic else facts

def keyword_filter_facts(facts, question, enable_general=False):
    if not facts:
        return facts
    q = question.lower()
    def fmatch(f, kw):
        return kw.replace(" ", "") in f.lower().replace(" ", "")
    if ("payment volume per transaction" in q) or ("average payment volume per transaction" in q):
        kept = []
        for f in facts:
            fl = f.lower()
            if "total volume" in fl:
                continue
            if fmatch(f, "payments volume") or fmatch(f, "total transactions"):
                kept.append(f)
        return kept if kept else facts
    if not enable_general:
        return facts
    keywords = [kw for kw in [
        "payments volume", "total volume", "total transactions", "transactions", "cards",
        "revenue", "income", "expense", "assets", "liabilities", "ratio", "percent", "%",
    ] if kw in q]
    if not keywords:
        return facts
    kept = [f for f in facts if any(fmatch(f, kw) for kw in keywords)]
    return kept if kept else facts

# ---------------- prompts（官方） ----------------
def build_prompt_baseline(context, question):
    return f"Context:\n{context}\n\nQuestion:\n{question}\n\nFinal Answer:"

def build_prompt_rag(facts, question):
    facts_block = "\n".join([f"- {f}" for f in facts])
    return f"FACTS:\n{facts_block}\n\nQUESTION:\n{question}\n\nFinal Answer:"

def build_prompt_structured(facts, question):
    facts_text = "\n".join([f"- {x}" for x in facts]) if facts else "(none)"
    ql = question.lower()
    extra_rule = ""
    if "cumulative total return" in ql:
        extra_rule = ("\nRULE:\nFor 'percentage cumulative total return' use:\n"
                      "((final_value - initial_value) / initial_value) * 100.\n"
                      "Use initial_value and final_value from FACTS (e.g., 31-dec-2012 and 31-dec-2017).\n")
    if ("payment volume per transaction" in ql) or ("average payment volume per transaction" in ql):
        extra_rule += ("\nRULE:\nFor 'payment volume per transaction', divide payments volume by total transactions.\n"
                       "Both are in the SAME unit (billions), so the unit cancels.\n"
                       "Use the raw numbers as given in FACTS (e.g., 637 and 5.0). Do NOT rescale.\n")
    normalization_rules = (
        "\nNORMALIZATION RULES:\n"
        "- IMPORTANT: DO NOT RESCALE numbers (e.g., do not turn 637 into 637,000,000).\n"
        "- If numerator and denominator share the same unit (e.g., both are in billions), the unit cancels: use raw numbers.\n"
        "- If the question asks for a percentage, return a percentage.\n"
        "- Keep the same unit unless explicitly asked to convert.\n"
        "- Do NOT convert units unless explicitly required.\n"
        "- For ratios or shares, use: (part / whole) * 100.\n"
    )
    return (f"FACTS:\n{facts_text}\n{extra_rule}{normalization_rules}\n"
            f"Question:\n{question}\n\nReturn ONLY the final numeric answer (optionally with %). No explanation.")

def build_prompt_mem0aug(remembered_text, context, question):
    return (f"Remembered facts (from long-term memory):\n{remembered_text}\n\n"
            + build_prompt_baseline(context, question))

# ---------------- 指标（官方，逐字移植 run_finqa_baseline_mem0.py） ----------------
_NUM_TOKEN_RE = re.compile(
    r"""(?P<paren>\(\s*)?(?P<sign>[-+])?(?P<num>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)(?P<paren_end>\s*\))?(?P<pct>\s*%)?""",
    re.VERBOSE,
)

def extract_last_number_with_flags(text):
    if text is None:
        return None
    t = str(text).strip()
    if not t:
        return None
    matches = list(_NUM_TOKEN_RE.finditer(t))
    if not matches:
        return None
    m = matches[-1]
    try:
        val = float(m.group("num").replace(",", ""))
    except ValueError:
        return None
    has_parens = (m.group("paren") is not None) and (m.group("paren_end") is not None)
    explicit_sign = m.group("sign")
    if has_parens and explicit_sign != "-":
        val = -val
    elif explicit_sign == "-":
        val = -abs(val)
    has_pct = m.group("pct") is not None
    return val, has_pct

def percent_expected(question, gold, pred):
    q = (question or "").lower()
    return ("%" in str(gold or "")) or ("%" in str(pred or "")) or ("percent" in q) or ("percentage" in q)

def decimals_in_gold(gold):
    s = str(gold or "").replace(",", "")
    m = re.search(r"\d+(?:\.(\d+))?", s)
    return len(m.group(1)) if m and m.group(1) else 0

def normalize_pred_to_gold_scale(question, gold, pred):
    g = extract_last_number_with_flags(gold)
    p = extract_last_number_with_flags(pred)
    if g is None or p is None:
        return None
    gval, g_pct = g
    pval, p_pct = p
    want_pct = percent_expected(question, gold, pred) or g_pct
    if want_pct and (not p_pct) and 0 <= abs(pval) <= 1.5:
        pval *= 100.0
    return pval, gval, want_pct

def exact_match(pred, gold, question=""):
    norm = normalize_pred_to_gold_scale(question, gold, pred)
    if norm is None:
        return False
    pval, gval, _ = norm
    decs = decimals_in_gold(gold)
    if decs == 0:
        return int(round(pval)) == int(round(gval))
    return round(pval, decs) == round(gval, decs)

def numeric_close(pred, gold, question="", atol=1e-2, rtol=1e-2):
    norm = normalize_pred_to_gold_scale(question, gold, pred)
    if norm is None:
        return False
    pval, gval, want_pct = norm
    decs = decimals_in_gold(gold)
    if want_pct:
        abs_tol = 0.5 if decs == 0 else (0.15 if decs == 1 else 0.05)
        return math.isclose(pval, gval, abs_tol=abs_tol, rel_tol=0.002)
    if decs == 0:
        abs_tol = 0.5 if abs(gval) < 1000 else max(1.0, abs(gval) * 0.001)
        return abs(pval - gval) <= abs_tol
    elif decs == 1:
        return abs(pval - gval) <= 0.15
    else:
        return abs(pval - gval) <= 0.05

def parse_success(text):
    return extract_last_number_with_flags(text) is not None
