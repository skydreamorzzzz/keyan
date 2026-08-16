"""构造 Strategy Memory：从 train 分层聚类 + LLM 抽象生成策略池。

决策记录：
- 覆盖 top-25 struct（累计 ~96% train），每个 struct 抽最多 6 个示例 case。
- 一个 struct 可以产出多个策略（同一程序形状可能对应不同语义，如 %change 与占比）。
- 策略必须不含：公司名、年份、具体数值、表行标签。全部用 operand 角色表示。
- 生成结果缓存到 output/strategies_raw.jsonl，可恢复；最后人工 QC 去重/修正。
"""
import json, os, re, random
from collections import defaultdict, Counter
import config
import finqa_common as fc
from llm import CachedLLM

SYSTEM_PROMPT = """You are an expert financial analyst building a library of REUSABLE reasoning STRATEGIES for answering financial QA over annual report tables and text (the FinQA benchmark).

Below is a small set of SOLVED example problems (each: question, gold supporting facts, gold reasoning program, answer).

Your job: group these examples into distinct reasoning strategies. For each group, produce ONE strategy that captures the common ABSTRACT method.

A strategy is an ABSTRACT method, NOT a copy of a program. It must NOT contain:
- company names, specific years, specific numbers from the examples, or specific table row labels.
Numbers should be referenced as named OPERANDS (e.g., new_value, old_value, part, whole, principal, rate, periods, row_values).

Use the FinQA program operators: add, subtract, multiply, divide, exp, greater, table_max, table_min, table_sum, table_average. In the "template" field, write a symbolic program using operand placeholders V1,V2,... (e.g., "divide(V1, V2)", "multiply(V1, exp(add(V3, V4), V5))", "table_sum(V1, none)").

Output STRICTLY a JSON array, one object per strategy, with EXACTLY these fields:
[
  {
    "name": "short semantic name",
    "problem_type": "one of: ratio, percentage_change, absolute_change, total_sum, average, table_aggregation, comparison, compound_interest, amortization, unit_conversion, proportion, growth_rate, shortfall_gap, difference, exchange_rate, per_unit, multiple, other",
    "problem_pattern": "when the question asks ..., the method is ...",
    "operand_roles": "definition of each operand and its role (e.g., V1=new_value, V2=old_value)",
    "procedure": "step-by-step abstract procedure (no specific numbers)",
    "formula": "human-readable formula (e.g., result = (new_value - old_value) / old_value)",
    "template": "symbolic FinQA program with V1,V2,... placeholders",
    "units_convention": "answer scale, percentage handling (fraction vs x100), const_ usage, unit conversions if any",
    "caveats": "known pitfalls for this strategy",
    "example_count": "how many examples it covers"
  }
]
Do not output anything outside the JSON array."""

def sample_examples(train_by_id, struct, n=6, seed=0):
    rng = random.Random(seed)
    pool = [x for x in train_by_id if tuple(x["struct"]) == struct]
    rng.shuffle(pool)
    return pool[:n]

def fmt_example(case):
    qa = case
    facts = " ; ".join(case["gold_facts"][:3])
    steps = " ; ".join(f"{s['op'].split('-')[0]}({s['arg1']},{s['arg2']})={s['res']}" for s in case["steps"][:6])
    return (f"--- example ---\n"
            f"Question: {qa['question']}\n"
            f"Facts: {facts}\n"
            f"Program (nested): {qa['program_re']}\n"
            f"Steps: {steps}\n"
            f"Answer: {qa['exe_ans']}")

def main():
    train = fc.load_train()
    cat = fc.load_cat()
    train_by_id = [{"question": x["qa"]["question"],
                    "gold_facts": fc.gold_fact_list(x["qa"]),
                    "program_re": x["qa"]["program_re"],
                    "steps": x["qa"]["steps"],
                    "exe_ans": x["qa"]["exe_ans"],
                    "struct": tuple(cat[x["id"]]["struct"]) if x["id"] in cat else (),
                    "id": x["id"]} for x in train]

    sc = Counter(t["struct"] for t in train_by_id)
    top_structs = [s for s, _ in sc.most_common(25)]
    print("generating strategies for", len(top_structs), "structs")

    llm = CachedLLM(os.path.join(config.OUT_DIR, "strategies_raw.jsonl"))
    items = []
    for si, struct in enumerate(top_structs):
        exs = sample_examples(train_by_id, struct, n=6, seed=si)
        if not exs:
            continue
        user = ("Here are the solved examples:\n\n" + "\n\n".join(fmt_example(e) for e in exs) +
                "\n\nNow output the JSON array of strategies (group the examples into 1-3 strategies).")
        key = f"strat_{si}_{struct}"
        items.append((key, [{"role": "user", "content": SYSTEM_PROMPT + "\n\n" + user}], {"max_tokens": 2000}))

    results = llm.run_batch(items)

    # parse JSON arrays
    strategies = []
    for si, struct in enumerate(top_structs):
        key = f"strat_{si}_{struct}"
        text = results.get(key, "")
        arr = None
        m = re.search(r'\[.*\]', text, re.S)
        if m:
            try:
                arr = json.loads(m.group(0))
            except Exception as e:
                print(f"[parse fail] {struct}: {str(e)[:80]}")
        if arr is None:
            print(f"[no json] {struct}: {text[:120]!r}")
            continue
        for s in arr:
            if not isinstance(s, dict) or "name" not in s:
                continue
            s["source_struct"] = list(struct)
            s["example_ids"] = [e["id"] for e in sample_examples(train_by_id, struct, n=6, seed=si)]
            strategies.append(s)

    # dedupe by template + problem_type
    seen = set(); dedup = []
    for s in strategies:
        tpl = str(s.get("template", "")).strip()
        pt = str(s.get("problem_type", "")).strip()
        key = (pt, tpl)
        if key in seen:
            continue
        seen.add(key)
        dedup.append(s)

    # assign ids
    for i, s in enumerate(dedup):
        s["strategy_id"] = f"S{i+1:03d}"
        s["retrieval_text"] = (f"Strategy: {s['name']}\nType: {s['problem_type']}\n"
                               f"Pattern: {s['problem_pattern']}\nTemplate: {s['template']}\n"
                               f"Units: {s['units_convention']}")

    out = os.path.join(config.OUT_DIR, "strategies.json")
    json.dump(dedup, open(out, "w"), indent=1, ensure_ascii=False)
    print(f"strategies: raw_calls={len(top_structs)} parsed={len(strategies)} dedup={len(dedup)} -> {out}")
    from collections import Counter as C2
    print("problem_type dist:", dict(C2(s.get("problem_type") for s in dedup)))
    for s in dedup:
        print(f"  {s['strategy_id']} [{s['problem_type']}] {s['name']} | {s['template']}")

if __name__ == "__main__":
    main()
