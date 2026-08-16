"""确定性抽取 ~20 条代表性样本并打印完整细节"""
import json, os, random

DATA = "/home/tiantian/keyan/data/finqa"
train = json.load(open(os.path.join(DATA, "train.json")))
by_id = {x["id"]: x for x in train}

cats = json.load(open("/home/tiantian/keyan/analysis/cat.json"))

def pick(pred, n, seed=0):
    rng = random.Random(seed)
    pool = [c for c in cats if pred(c)]
    rng.shuffle(pool)
    return pool[:n]

# Selection targets
sel = []
# A: comparison / yes-no
sel += pick(lambda c: c["struct"] == ("greater",), 2, 1)
sel += pick(lambda c: c["struct"][-1] == "greater" and len(c["struct"]) > 1, 1, 2)
# B: table aggregation
sel += pick(lambda c: c["struct"] == ("table_average",), 1, 3)
sel += pick(lambda c: c["struct"] == ("table_sum",), 1, 4)
sel += pick(lambda c: c["struct"] == ("table_max",), 1, 5)
# C: unit scaling multi-step (const in 3+ step)
sel += pick(lambda c: c["uses_const"] and c["nstep"] >= 3 and "multiply" in c["ops"], 3, 6)
# D: 4+ steps
sel += pick(lambda c: c["nstep"] >= 4, 2, 7)
# E: 3-step (no const, no table op)
sel += pick(lambda c: c["nstep"] == 3 and not c["uses_const"] and not c["uses_table_op"], 2, 8)
# F: 2-step typical
sel += pick(lambda c: c["struct"] == ("subtract", "divide"), 1, 9)
sel += pick(lambda c: c["struct"] == ("add", "divide"), 1, 10)
sel += pick(lambda c: c["nstep"] == 2 and c["num_text"] >= 1 and c["num_table"] >= 1, 1, 11)
sel += pick(lambda c: c["nstep"] == 2 and c["uses_const"], 1, 12)
# G: 1-step
sel += pick(lambda c: c["struct"] == ("divide",), 1, 13)
sel += pick(lambda c: c["struct"] == ("subtract",), 1, 14)
sel += pick(lambda c: c["struct"] == ("add",), 1, 15)
sel += pick(lambda c: c["struct"] == ("multiply",), 1, 16)

# dedup by id
seen, final = set(), []
for c in sel:
    if c["id"] not in seen:
        seen.add(c["id"]); final.append(c)
print("selected:", len(final))

out = []
for c in final:
    x = by_id[c["id"]]
    qa = x["qa"]
    rec = {
        "id": x["id"],
        "question": qa["question"],
        "program": qa["program"],
        "program_re": qa["program_re"],
        "exe_ans": qa["exe_ans"],
        "answer": qa.get("answer"),
        "explanation": qa.get("explanation"),
        "gold_inds": qa["gold_inds"],
        "steps": qa["steps"],
        "ann_table_rows": qa.get("ann_table_rows"),
        "ann_text_rows": qa.get("ann_text_rows"),
        "pre_text": x["pre_text"],
        "post_text": x["post_text"],
        "table": x["table"],
    }
    out.append(rec)

with open("/home/tiantian/keyan/analysis/sample20_dump.json", "w") as f:
    json.dump(out, f, indent=1, ensure_ascii=False)
print("dumped sample20_dump.json")
for r in out:
    print(f"\n===== {r['id']} =====")
    print("Q:", r["question"])
    print("prog:", r["program_re"])
    print("ans:", r["exe_ans"], "| answer field:", r["answer"])
