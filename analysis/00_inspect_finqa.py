"""FinQA 数据结构检查脚本（Stage 1 可行性分析）"""
import json, os, collections, re, sys

DATA = "/home/tiantian/keyan/data/finqa"

def load(split):
    with open(os.path.join(DATA, f"{split}.json")) as f:
        return json.load(f)

def report_of(eid):
    # id format: "<report>/page_X.pdf-<index>" e.g. "ETR/2016/page_23.pdf-2"
    m = re.match(r"^(.*/page_\d+\.pdf)-(\d+)$", eid)
    if m:
        return m.group(1)
    return eid

def main():
    splits = {}
    for s in ["train", "dev", "test", "private_test"]:
        p = os.path.join(DATA, f"{s}.json")
        if os.path.exists(p):
            splits[s] = load(s)
    print("=== 1. Split sizes ===")
    for s, d in splits.items():
        print(f"  {s}: {len(d)}")

    # ---- structural check on train ----
    print("\n=== 2. Field structure (train[0]) ===")
    train = splits["train"]
    s0 = train[0]
    print("  top-level keys:", list(s0.keys()))
    print("  qa keys:", list(s0["qa"].keys()))
    print("  sample id:", s0["id"])
    print("  sample question:", s0["qa"]["question"][:120])
    print("  sample program:", s0["qa"]["program"])
    print("  sample program_re:", json.dumps(s0["qa"]["program_re"])[:300])
    print("  gold_inds:", s0["qa"]["gold_inds"], "| type:", type(s0["qa"]["gold_inds"]).__name__)
    print("  exe_ans:", s0["qa"]["exe_ans"])

    print("\n  pre_text (first 2 sentences):")
    for i, t in enumerate(s0["pre_text"][:2]):
        print(f"    [{i}] {t[:120]}")
    print("  post_text (first 2):")
    for i, t in enumerate(s0["post_text"][:2]):
        print(f"    [{i}] {t[:120]}")
    print("  table shape: rows=", len(s0["table"]), "cols=", len(s0["table"][0]) if s0["table"] else 0)
    print("  table header:", s0["table"][0] if s0["table"] else None)
    print("  table row 1:", s0["table"][1] if len(s0["table"]) > 1 else None)

    # ---- report sharing within splits ----
    print("\n=== 3. Report sharing (multiple Q per report) ===")
    for s, d in splits.items():
        reps = collections.Counter(report_of(x["id"]) for x in d)
        multi = {k: v for k, v in reps.items() if v > 1}
        print(f"  {s}: distinct reports={len(reps)}, questions={len(d)}, "
              f"reports with >1 Q={len(multi)} ({100*len(multi)/max(len(reps),1):.1f}%), "
              f"max Q in one report={max(reps.values()) if reps else 0}")

    # ---- cross-split report overlap ----
    print("\n=== 4. Cross-split report/company overlap ===")
    rep_sets = {s: set(report_of(x["id"]) for x in d) for s, d in splits.items()}
    company_of = lambda r: r.split("/")[0] if "/" in r else r
    comp_sets = {s: set(company_of(report_of(x["id"])) for x in d) for s, d in splits.items()}
    pairs = [("train", "dev"), ("train", "test"), ("dev", "test"),
             ("train", "private_test"), ("dev", "private_test")]
    for a, b in pairs:
        if a in rep_sets and b in rep_sets:
            ro = len(rep_sets[a] & rep_sets[b])
            co = len(comp_sets[a] & comp_sets[b])
            print(f"  {a} vs {b}: shared reports={ro}, shared companies={co}")

    # ---- program structure ----
    print("\n=== 5. Program structure (train) ===")
    ops = collections.Counter()
    lens = []
    for x in train:
        p = x["qa"]["program"]
        for tok in p:
            m = re.match(r"^([a-zA-Z_]+)\(", tok)
            if m:
                ops[m.group(1)] += 1
        lens.append(len(p))
    print("  operator frequencies:", dict(ops.most_common()))
    print("  program length: min=%d max=%d mean=%.1f" % (min(lens), max(lens), sum(lens)/len(lens)))
    print("  program_re is nested list? sample:", train[0]["qa"]["program_re"][:1])

    # scale of answers
    print("\n  exe_ans sample values:", [str(x["qa"]["exe_ans"]) for x in train[:10]])

if __name__ == "__main__":
    main()
