"""FinQA 深层次结构检查：字段类型、新增字段含义、gold_inds 语义、program 解析"""
import json, os, collections, re

DATA = "/home/tiantian/keyan/data/finqa"
train = json.load(open(os.path.join(DATA, "train.json")))
dev = json.load(open(os.path.join(DATA, "dev.json")))
test = json.load(open(os.path.join(DATA, "test.json")))
priv = json.load(open(os.path.join(DATA, "private_test.json")))

print("=== field presence across splits ===")
for split, d in [("train", train), ("dev", dev), ("test", test), ("private_test", priv)]:
    keys = collections.Counter()
    qakeys = collections.Counter()
    for x in d:
        for k in x.keys(): keys[k] += 1
        for k in x.get("qa", {}).keys(): qakeys[k] += 1
    print(f"\n{split} (n={len(d)}): top-level fields:")
    for k, c in keys.most_common(): print(f"    {k}: {c}")
    print(f"  qa fields:")
    for k, c in qakeys.most_common(): print(f"    {k}: {c}")

print("\n=== types of key fields (train) ===")
s = train[0]["qa"]
for k in ["program", "program_re", "gold_inds", "exe_ans", "answer", "explanation", "steps",
          "ann_table_rows", "ann_text_rows", "tfidftopn", "model_input"]:
    print(f"  {k}: type={type(s[k]).__name__}")
    val = s[k]
    if isinstance(val, str): print(f"      sample: {val[:150]}")
    elif isinstance(val, (list, dict)): print(f"      sample: {json.dumps(val)[:200]}")
    else: print(f"      sample: {val}")

print("\n=== a sample with full detail (train[1]) ===")
s1 = train[1]
print("id:", s1["id"])
print("filename:", s1.get("filename"))
print("table_ori is same as table?", s1.get("table_ori") == s1.get("table"))
print("question:", s1["qa"]["question"])
print("answer:", s1["qa"].get("answer"))
print("explanation:", (s1["qa"].get("explanation") or "")[:200])
print("program:", s1["qa"]["program"])
print("program_re:", s1["qa"]["program_re"])
print("gold_inds:", json.dumps(s1["qa"]["gold_inds"]))
print("steps:", json.dumps(s1["qa"].get("steps"))[:300])
print("ann_table_rows:", s1["qa"].get("ann_table_rows"))
print("ann_text_rows:", s1["qa"].get("ann_text_rows"))
print("exe_ans:", s1["qa"]["exe_ans"])
print("pre_text:", s1["pre_text"][:3])
print("post_text:", s1["post_text"][:3])
print("table:", json.dumps(s1["table"], ensure_ascii=False)[:300])

print("\n=== how gold_inds relate to table/text (test on train[0]) ===")
s0 = train[0]
print("pre_text[1]:", s0["pre_text"][1])
print("gold_inds:", s0["qa"]["gold_inds"])
print("table_retrieved keys:", list(s0.get("table_retrieved", {}).keys()) if isinstance(s0.get("table_retrieved"), dict) else type(s0.get("table_retrieved")))

print("\n=== program is string or list? check parseability ===")
p0 = train[0]["qa"]["program"]
print("  type:", type(p0).__name__, "| repr:", repr(p0)[:80])
# try the official-style token split
toks = [t.strip() for t in p0.split(",")]
print("  split by comma:", toks)

print("\n=== operator histogram (from program_re) ===")
ops = collections.Counter()
for x in train:
    pr = x["qa"]["program_re"]
    if isinstance(pr, str):
        for m in re.findall(r"([a-z_]+)\(", pr):
            ops[m] += 1
print("  operators:", dict(ops.most_common()))
