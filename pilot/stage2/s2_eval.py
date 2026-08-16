"""Stage 2 评估：
- reproduction metric：论文的 Corrected Exact / Close（free-form 输出 + 符号归一化，见论文 III-C）。
  归一化：取最后一个数值 token、会计负数、fraction<->percent 视题面、gold 精度自适应容差。
  具体容差未在论文给出，以下为文档化假设。
- unified reasoning metric：FinQA 官方 execution accuracy / program 结构匹配（复用 pilot/executor）。
"""
import re, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from executor import exec_program_re, match_result, canonical_re, normalize_program

PERCENT_KW = ["percent", "%", "growth", "change", "ratio", "rate", "return", "basis", "increase", "decrease", "portion"]

def extract_numeric(text):
    """从 free-form 输出提取最后一个数值。支持逗号、百分比、会计负数。返回 float 或 None。"""
    if not text:
        return None
    # 会计负数 (123) -> -123；"-123"; "1,234.5"; "12%"
    toks = re.findall(r"\(?\s*-?\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*\)?\s*%?", text)
    if not toks:
        return None
    last = toks[-1].strip()
    if last.endswith("%"):
        last = last[:-1].strip()
    neg = False
    if last.startswith("(") and last.endswith(")"):
        neg = True
        last = last[1:-1].strip()
    elif last.startswith("-"):
        neg = True
        last = last[1:].strip()
    last = last.replace(",", "")
    try:
        v = float(last)
        return -v if neg else v
    except ValueError:
        return None

def candidates(pred, gold, question):
    """候选数值集。percent 语境下允许 ×100 / ÷100。"""
    base = [pred]
    q = question.lower()
    percent_ctx = any(kw in q for kw in PERCENT_KW) or (isinstance(gold, (int, float)) and abs(float(gold)) < 0.5)
    if percent_ctx:
        base += [pred * 100.0, pred / 100.0]
    return base

def close_ok(cand, gold):
    g = float(gold)
    rel = 0.01
    abs_tol = 0.5 if abs(g) >= 1.0 else 0.01
    return abs(cand - g) <= max(rel * abs(g), abs_tol)

def corrected_metrics(raw, gold, question):
    """返回 (corrected_exact, corrected_close, parsed)。"""
    pred = extract_numeric(raw)
    if pred is None or gold in ("yes", "no") or not isinstance(gold, (int, float)):
        return False, False, pred
    g = float(gold)
    exact = any(abs(c - g) <= max(1e-4, 1e-4 * abs(g)) for c in candidates(pred, g, question))
    close = any(close_ok(c, g) for c in candidates(pred, g, question))
    return exact, close, pred

# ---------------- FinQA unified metrics ----------------
def finqa_exec(raw, table, gold_ans):
    okp, res = exec_program_re(raw, table)
    return okp and match_result(res, gold_ans)

def finqa_struct(raw, gold_re):
    pc = canonical_re(normalize_program(raw))
    return pc is not None and pc == canonical_re(gold_re)
