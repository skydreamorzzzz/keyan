"""构造 Case Memory（train 全量，直接取原数据，不重写）。

决策记录：
- Case = 一个 train 样本。字段全部来自原数据 + 最小派生。
- 检索文本 = question + problem_kind(bucket) + gold_facts 渲染事实。
- 不引入任何 LLM 重写（第一版保持"真实案例"），避免污染与成本。
- 保留 full context 引用（report 路径），prompt 阶段按需取用。
"""
import json, os
import config
import finqa_common as fc

def main():
    train = fc.load_train()
    cat = fc.load_cat()

    cases = []
    for x in train:
        qa = x["qa"]
        c = cat.get(x["id"])
        if c is None:
            c = {"nstep": 0, "ops": [], "uses_table_op": False, "uses_greater": False,
                 "uses_const": False, "num_text": 0, "num_table": 0, "struct": []}
        b = fc.bucket(c)
        facts = fc.gold_fact_list(qa)
        retrieval_text = (
            f"Question: {qa['question']}\n"
            f"Type: {b}\n"
            f"Facts: " + " ; ".join(facts)
        )
        cases.append({
            "case_id": x["id"],
            "report": fc.report_of(x["id"]),
            "company": fc.company_of(x["id"]),
            "question": qa["question"],
            "problem_kind": b,
            "n_steps": c["nstep"],
            "struct": c["struct"],
            "gold_facts": facts,
            "program": qa["program"],
            "program_re": qa["program_re"],
            "steps": qa["steps"],
            "exe_ans": qa["exe_ans"],
            "answer": qa.get("answer"),
            "explanation": qa.get("explanation") or "",
            "retrieval_text": retrieval_text,
        })

    out = os.path.join(config.OUT_DIR, "case_memory.json")
    os.makedirs(config.OUT_DIR, exist_ok=True)
    with open(out, "w") as f:
        json.dump(cases, f, ensure_ascii=False)
    print(f"case_memory.json: {len(cases)} cases -> {out}")
    # bucket 分布
    from collections import Counter
    print("bucket dist:", dict(Counter(c["problem_kind"] for c in cases)))

if __name__ == "__main__":
    main()
