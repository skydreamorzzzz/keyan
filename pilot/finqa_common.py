"""FinQA 共享工具：id 解析、bucket 分类、上下文格式化。"""
import json, re, os
import config

def report_of(eid):
    m = re.match(r"^(.*/page_\d+\.pdf)-(\d+)$", eid)
    return m.group(1) if m else eid

def company_of(eid):
    return report_of(eid).split("/")[0]

def load_train():
    return json.load(open(os.path.join(config.DATA_DIR, "train.json")))

def load_cat():
    """Stage 1 的 cat.json：id -> 结构元信息。"""
    cats = json.load(open("/home/tiantian/keyan/analysis/cat.json"))
    return {c["id"]: c for c in cats}

def bucket(cat):
    if cat["uses_greater"]:
        return "A_comparison_yesno"
    if cat["uses_table_op"]:
        return "B_table_aggregation"
    if cat["uses_const"] and cat["nstep"] >= 3:
        return "C_unitscaling_multi"
    if cat["nstep"] >= 4:
        return "D_multistep4plus"
    if cat["nstep"] == 3:
        return "E_3step"
    if cat["nstep"] == 2:
        return "F_2step"
    if cat["nstep"] == 1:
        return "G_1step"
    return "H_other"

def format_table(table):
    """表格 -> 便于 LLM 阅读的文本。"""
    lines = []
    for i, row in enumerate(table):
        lines.append(f"row{i}: " + " | ".join(str(c) for c in row))
    return "\n".join(lines)

def format_context(pre_text, post_text, table, max_pre=30, max_post=30):
    """报告上下文 -> 文本。截断长文本（决策：pilot 阶段截断，避免 token 爆炸；记录截断率）。"""
    pre = "\n".join(f"s{i}: {t}" for i, t in enumerate(pre_text[:max_pre]))
    post = "\n".join(f"t{i}: {t}" for i, t in enumerate(post_text[:max_post]))
    tbl = format_table(table)
    parts = [f"TEXT BEFORE TABLE:\n{pre}", f"TEXT AFTER TABLE:\n{post}", f"TABLE:\n{tbl}"]
    return "\n\n".join(parts)

def gold_fact_list(qa):
    """gold_inds -> 事实文本列表。"""
    return list(qa["gold_inds"].values())

def compute_cat(x):
    """对任意样本计算结构元信息（dev/test 也适用），与 Stage 1 cat.json 同构。"""
    from executor import parse_linear_steps
    qa = x["qa"]
    try:
        steps = parse_linear_steps(qa["program"])
    except Exception:
        steps = []
    ops = [s[0] for s in steps]
    prog = qa.get("program") or ""
    gi = qa["gold_inds"]
    return {
        "nstep": len(steps), "ops": ops, "struct": list(ops),
        "uses_table_op": any(o.startswith("table_") for o in ops),
        "uses_greater": "greater" in ops,
        "uses_const": "const_" in prog,
        "num_text": sum(1 for k in gi if k.startswith("text_")),
        "num_table": sum(1 for k in gi if k.startswith("table_")),
    }
