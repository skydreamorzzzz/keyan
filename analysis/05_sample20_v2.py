"""确定性抽取 20 条多样化样本（v2，更鲁棒）"""
import json, os, random

DATA = "/home/tiantian/keyan/data/finqa"
train = json.load(open(os.path.join(DATA, "train.json")))
by_id = {x["id"]: x for x in train}
cats = json.load(open("/home/tiantian/keyan/analysis/cat.json"))
for c in cats:
    c["struct"] = tuple(c["struct"])
cat_by_id = {c["id"]: c for c in cats}

rng = random.Random(42)

def sample_struct(struct, n):
    pool = [c for c in cats if c["struct"] == struct]
    rng.shuffle(pool)
    return pool[:n]

def sample_pred(pred, n):
    pool = [c for c in cats if pred(c)]
    rng.shuffle(pool)
    return pool[:n]

# explicit per-struct budget (20)
plan = [
    ("G_div1",   lambda: sample_struct(("divide",), 2)),
    ("G_sub1",   lambda: sample_struct(("subtract",), 1)),
    ("G_add1",   lambda: sample_struct(("add",), 1)),
    ("G_mul1",   lambda: sample_struct(("multiply",), 1)),
    ("G_tavg",   lambda: sample_struct(("table_average",), 1)),
    ("G_tsum",   lambda: sample_struct(("table_sum",), 1)),
    ("G_tmax",   lambda: sample_struct(("table_max",), 1)),
    ("F_subdiv", lambda: sample_struct(("subtract", "divide"), 2)),
    ("F_adddiv", lambda: sample_struct(("add", "divide"), 1)),
    ("F_divsub", lambda: sample_struct(("divide", "subtract"), 1)),
    ("F_t2",     lambda: sample_pred(lambda c: c["nstep"] == 2 and c["num_text"] >= 1 and c["num_table"] >= 1, 1)),
    ("F_c2",     lambda: sample_pred(lambda c: c["nstep"] == 2 and c["uses_const"], 1)),
    ("E_3",      lambda: sample_pred(lambda c: c["nstep"] == 3 and not c["uses_const"] and not c["uses_table_op"], 1)),
    ("C_mulc",   lambda: sample_pred(lambda c: c["uses_const"] and c["nstep"] >= 3 and "multiply" in c["ops"], 1)),
    ("D_4p",     lambda: sample_pred(lambda c: c["nstep"] >= 4 and not c["uses_const"] and not c["uses_greater"], 1)),
    ("A_gr",     lambda: sample_struct(("greater",), 1)),
    ("A_grN",    lambda: sample_pred(lambda c: c["struct"][-1] == "greater" and len(c["struct"]) > 1, 1)),
]
seen, picked = set(), []
for name, fn in plan:
    for c in fn():
        if c["id"] in seen: continue
        seen.add(c["id"]); picked.append((name, c))
        break

print("picked:", len(picked))
with open("/home/tiantian/keyan/analysis/sample20_ids.json", "w") as f:
    json.dump([{"name": n, "id": c["id"]} for n, c in picked], f, indent=1)

# dump full detail
out = []
for name, c in picked:
    x = by_id[c["id"]]
    qa = x["qa"]
    out.append({
        "name": name, "id": x["id"], "question": qa["question"],
        "program": qa["program"], "program_re": qa["program_re"],
        "exe_ans": qa["exe_ans"], "answer": qa.get("answer"),
        "explanation": qa.get("explanation"), "gold_inds": qa["gold_inds"],
        "steps": qa["steps"], "ann_table_rows": qa.get("ann_table_rows"),
        "ann_text_rows": qa.get("ann_text_rows"),
        "pre_text": x["pre_text"], "post_text": x["post_text"], "table": x["table"],
    })
with open("/home/tiantian/keyan/analysis/sample20_dump.json", "w") as f:
    json.dump(out, f, indent=1, ensure_ascii=False)
print("dumped", len(out))
for r in out:
    print(f"\n== {r['name']} | {r['id']}")
    print("  Q:", r["question"])
    print("  prog:", r["program_re"])
    print("  ans:", r["exe_ans"])
