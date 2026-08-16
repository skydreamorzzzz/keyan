"""按推理类型对 FinQA train 分层，供 20 条抽样分析"""
import json, os, re, collections

DATA = "/home/tiantian/keyan/data/finqa"
train = json.load(open(os.path.join(DATA, "train.json")))

ALL_OPS = ["add", "subtract", "multiply", "divide", "exp", "greater",
           "table_max", "table_min", "table_sum", "table_average"]

def program_tokenization(prog):
    prog = prog.split(", ")
    tokens = []
    for tok in prog:
        cur = ''
        for c in tok:
            if c == ')':
                if cur: tokens.append(cur); cur = ''
            cur += c
            if c in '()':
                tokens.append(cur); cur = ''
        if cur: tokens.append(cur)
    return tokens

def parse_steps(prog):
    """returns list of (op, arg1, arg2)"""
    toks = program_tokenization(prog)
    steps = []
    i = 0
    while i + 3 < len(toks):
        op = toks[i].strip('(')
        if op not in ALL_OPS:
            break
        steps.append((op, toks[i+1], toks[i+2]))
        i += 4
    return steps

def categorize(x):
    qa = x["qa"]
    steps = parse_steps(qa["program"])
    ops = [s[0] for s in steps]
    nstep = len(steps)
    uses_table_op = any(o.startswith("table_") for o in ops)
    uses_greater = "greater" in ops
    uses_const = "const_" in qa["program"]
    num_text = sum(1 for k in qa["gold_inds"] if k.startswith("text_"))
    num_table = sum(1 for k in qa["gold_inds"] if k.startswith("table_"))
    # simplify to canonical structure: replace numbers with x
    struct = tuple(o for o in ops)
    is_yesno = qa["exe_ans"] in ("yes", "no")
    return dict(steps=steps, ops=ops, nstep=nstep, uses_table_op=uses_table_op,
                uses_greater=uses_greater, uses_const=uses_const,
                num_text=num_text, num_table=num_table, struct=struct, is_yesno=is_yesno)

cat = []
for x in train:
    c = categorize(x)
    c["id"] = x["id"]
    c["question"] = x["qa"]["question"]
    c["exe_ans"] = x["qa"]["exe_ans"]
    cat.append(c)

# bucket definitions (priority order)
def bucket(c):
    if c["uses_greater"]: return "A_comparison_yesno"
    if c["uses_table_op"]: return "B_table_aggregation"
    if c["uses_const"] and c["nstep"] >= 3: return "C_unitscaling_multi"
    if c["nstep"] >= 4: return "D_multistep4plus"
    if c["nstep"] == 3: return "E_3step"
    if c["nstep"] == 2: return "F_2step"
    if c["nstep"] == 1: return "G_1step"
    return "H_other"

from collections import defaultdict
groups = defaultdict(list)
for c in cat:
    groups[bucket(c)].append(c)

print("=== bucket sizes ===")
for k in sorted(groups): print(f"  {k}: {len(groups[k])}")

print("\n=== struct distribution (top) ===")
sc = collections.Counter(c["struct"] for c in cat)
for s, n in sc.most_common(15):
    print(f"  {s} x{n}")

# save parsed structures to disk for later reuse
with open("/home/tiantian/keyan/analysis/cat.json", "w") as f:
    json.dump([{k: c[k] for k in ["id","question","exe_ans","struct","nstep","ops","uses_table_op",
                                   "uses_greater","uses_const","num_text","num_table","is_yesno"]} for c in cat], f)
print("\nsaved cat.json")
