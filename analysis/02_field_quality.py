"""检查字段填充率、gold_inds 索引语义、retrieved 字段与 gold 的关系、question 类型分布"""
import json, os, collections, re

DATA = "/home/tiantian/keyan/data/finqa"
train = json.load(open(os.path.join(DATA, "train.json")))

def is_blank(v):
    if v is None: return True
    if isinstance(v, str): return v.strip() == ""
    if isinstance(v, (list, dict)): return len(v) == 0
    return False

print("=== fill rates (train) ===")
for field in ["answer", "explanation", "steps", "ann_table_rows", "ann_text_rows", "gold_inds", "program_re"]:
    filled = sum(1 for x in train if not is_blank(x["qa"].get(field)))
    print(f"  qa.{field}: {filled}/{len(train)} ({100*filled/len(train):.1f}%)")

# explanation length distribution
lens = [len(x["qa"]["explanation"]) for x in train]
print("  explanation length: min=%d max=%d" % (min(lens), max(lens)))
print("  explanation sample (non-empty):", [x["qa"]["explanation"][:100] for x in train if len(x["qa"]["explanation"])>0][:3])

print("\n=== gold_inds indexing semantics (verify text_N maps to pre+post concat) ===")
ok = 0; fail = []
for x in train[:500]:
    pre, post = x["pre_text"], x["post_text"]
    concat = pre + post
    for k, v in x["qa"]["gold_inds"].items():
        if k.startswith("text_"):
            idx = int(k.split("_")[1])
            # compare normalized
            if idx < len(concat) and concat[idx] == v:
                ok += 1
            else:
                fail.append((k, v[:40], concat[idx][:40] if idx < len(concat) else "OOB"))
        elif k.startswith("table_"):
            trow = int(k.split("_")[1])
            # table rows: header is row 0
            if trow < len(x["table"]):
                rowtxt = " ; ".join(x["table"][trow])
                if rowtxt[:40] in v or v[:40] in rowtxt: ok += 1
                else: fail.append((k, v[:40], rowtxt[:40]))
print("  matches in first 500:", ok)
print("  sample failures:", fail[:8])

print("\n=== gold_inds: how many text vs table facts per sample ===")
tc = collections.Counter();
for x in train:
    gi = x["qa"]["gold_inds"]
    t = sum(1 for k in gi if k.startswith("text_"))
    tb = sum(1 for k in gi if k.startswith("table_"))
    tc[(t, tb)] += 1
print("  (num_text, num_table) histogram top:", tc.most_common(12))

print("\n=== retrieved fields ===")
s = train[0]
print("  table_retrieved type:", type(s["table_retrieved"]).__name__, "| first item:", str(s["table_retrieved"])[:200])
print("  text_retrieved type:", type(s["text_retrieved"]).__name__, "| first item:", str(s["text_retrieved"])[:200])
print("  table_retrieved_all type:", type(s["table_retrieved_all"]).__name__)
print("  text_retrieved_all type:", type(s["text_retrieved_all"]).__name__)

print("\n=== does 'table_retrieved' equal gold table rows? (compare with gold_inds table keys) ===")
match = 0; nm = 0
for x in train[:300]:
    gold_tbl = {k for k in x["qa"]["gold_inds"] if k.startswith("table_")}
    # retrieved rows: whatever structure
    tr = x["table_retrieved"]
    trs = set()
    if isinstance(tr, dict): trs = set(tr.keys())
    elif isinstance(tr, list): trs = {str(t) for t in tr}
    if gold_tbl == trs: match += 1
    else: nm += 1
print(f"  exact key match gold vs table_retrieved: {match}/{nm+match}")

print("\n=== question types ===")
def qtype(q):
    ql = q.lower()
    if ql.startswith(("is ", "are ", "was ", "were ", "did ", "does ", "do ", "has ", "have ", "can ", "will ")): return "yes/no?"
    if ql.startswith("what "): return "what"
    if ql.startswith("how much"): return "how_much"
    if ql.startswith("how many"): return "how_many"
    return "other"
tc = collections.Counter(qtype(x["qa"]["question"]) for x in train)
print("  question-type distribution:", dict(tc.most_common()))

print("\n=== exe_ans value types ===")
at = collections.Counter()
for x in train:
    a = x["qa"]["exe_ans"]
    if isinstance(a, bool): at["bool"] += 1
    elif isinstance(a, (int, float)): at["number"] += 1
    elif isinstance(a, str):
        at["str:"+a.lower() if a.lower() in ("yes","no") else "str-other"] += 1
    else: at[type(a).__name__] += 1
print("  exe_ans types:", dict(at))
ys = sum(1 for x in train if x["qa"]["exe_ans"] == "yes")
print(f"  'yes' answers: {ys}")

print("\n=== const_* tokens usage in programs ===")
ct = collections.Counter()
for x in train:
    for m in re.findall(r"const_[0-9]+", x["qa"]["program"]):
        ct[m] += 1
print("  const tokens:", dict(ct.most_common()))
