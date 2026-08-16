"""排查 structured 臂过弱的原因：
1) gold 文本事实比例（table-only structured 会丢 text facts）
2) gold 数值 operand 是否在检索 top-k 内（RAG vs Structured）
3) structured 输出可解析率 / 失败模式
"""
import json, os, sys, re, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import s2config as config
from s2_facts import doc_to_rag_facts, table_to_structured_facts, composite_filter
from s2_retrieval import retrieve_facts
from executor import exec_program_re
import finqa_common as fc

def gold_nums(program_re):
    """gold program_re 里的数值字面量（去掉 const）。"""
    nums = re.findall(r"(?<![a-z_])(-?\d+(?:\.\d+)?)\s*%?", program_re)
    return [float(n) for n in nums]

def nums_in_facts(facts):
    out = set()
    for f in facts:
        for m in re.findall(r"-?\d+(?:\.\d+)?", f["fact"]):
            out.add(float(m))
    return out

def main():
    dev = {x["id"]: x for x in json.load(open(os.path.join(config.DATA, "dev.json")))}
    import random
    pool = [x["id"] for x in json.load(open(os.path.join(config.DATA, "dev.json")))]
    random.Random(config.SAMPLE_SEED).shuffle(pool)
    ids = pool[:config.SAMPLE_N]
    outs = json.load(open(os.path.join(config.OUT, "arm_outputs.json")))

    text_fact_q = 0   # 需要文本事实（gold_inds 含 text_）
    only_text = 0     # 只靠文本（无 table 事实）
    n = 0
    cov_rag = cov_struct = 0
    parse_s = parse_b = 0
    examples = []
    for qid in ids:
        x = dev[qid]
        q = x["qa"]["question"]
        n += 1
        gi = x["qa"]["gold_inds"]
        has_text = any(k.startswith("text_") for k in gi)
        has_table = any(k.startswith("table_") for k in gi)
        if has_text: text_fact_q += 1
        if has_text and not has_table: only_text += 1

        golds = gold_nums(x["qa"]["program_re"])
        rag_all = doc_to_rag_facts(x["pre_text"], x["post_text"], x["table"])
        struct_all = composite_filter(table_to_structured_facts(x["table"]))
        rag_top = retrieve_facts(q, rag_all, config.RETRIEVAL_K)
        struct_top = retrieve_facts(q, struct_all, config.RETRIEVAL_K)
        rag_nums = nums_in_facts(rag_top)
        struct_nums = nums_in_facts(struct_top)
        cov_rag += sum(1 for g in golds if g in rag_nums) >= max(1, len(golds))  # 全部覆盖才算
        # 部分覆盖更宽容
        cov_rag += 0
        # 结构：文本事实问题里 structured 是否可能失败
        raw_s = outs["unified"]["structured"].get(qid, "")
        okp, res = exec_program_re(raw_s, x["table"])
        parse_s += okp
        raw_b = outs["unified"]["baseline"].get(qid, "")
        okp_b, _ = exec_program_re(raw_b, x["table"])
        parse_b += okp_b
        if has_text and not has_table and len(examples) < 6:
            examples.append((qid, q[:90], x["qa"]["program_re"][:70], raw_s[:80]))

    print(f"n={n}")
    print(f"需要文本事实的样本: {text_fact_q} ({100*text_fact_q/n:.0f}%)；仅文本无表格: {only_text} ({100*only_text/n:.0f}%)")
    print(f"structured 可执行率: {parse_s/n:.3f}  baseline 可执行率: {parse_b/n:.3f}")
    print("仅文本事实的样本示例（structured 臂输出）:")
    for qid, q, gold, raw in examples:
        print(f"  {qid}: Q={q}\n      gold={gold}\n      struct_raw={raw}")

if __name__ == "__main__":
    main()
