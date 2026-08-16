"""Stage 2 评估：
1) reproduction：论文 Corrected Exact/Close（free-form 臂）
2) unified：FinQA execution/program（program 臂）
3) 增量分析：Structured 之上加 Case/Strategy 的增益 + 互补性重算（Case-only/Strategy-only/干扰/Oracle/Gap）
"""
import json, os, sys, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import s2config as config
from s2_eval import corrected_metrics, finqa_exec, finqa_struct

def main():
    dev = {x["id"]: x for x in json.load(open(os.path.join(config.DATA, "dev.json")))}
    outs = json.load(open(os.path.join(config.OUT, "arm_outputs.json")))
    # sample ids in order (deterministic)
    import random
    pool = [x["id"] for x in json.load(open(os.path.join(config.DATA, "dev.json")))]
    random.Random(config.SAMPLE_SEED).shuffle(pool)
    ids = pool[:config.SAMPLE_N]
    n = len(ids)

    print(f"n={n}")
    print("\n===== REPRODUCTION (Corrected Exact / Close) =====")
    repro = {}
    for arm in config.REPRO_ARMS:
        ex = cl = parse = 0
        for qid in ids:
            raw = outs["repro"][arm].get(qid, "")
            gold = dev[qid]["qa"]["exe_ans"]
            q = dev[qid]["qa"]["question"]
            e, c, pred = corrected_metrics(raw, gold, q)
            ex += e; cl += c; parse += pred is not None
        repro[arm] = {"exact": ex/n, "close": cl/n, "parse": parse/n}
        print(f"  {arm:12s} Corr.Exact={ex/n:.3f}  Corr.Close={cl/n:.3f}  Parse={parse/n:.3f}")

    print("\n===== UNIFIED (FinQA exec / program) =====")
    unified = {}
    for arm in config.UNIFIED_ARMS:
        ex = st = 0
        for qid in ids:
            raw = outs["unified"][arm].get(qid, "")
            x = dev[qid]
            ex += finqa_exec(raw, x["table"], x["qa"]["exe_ans"])
            st += finqa_struct(raw, x["qa"]["program_re"])
        unified[arm] = {"exec": ex/n, "program": st/n}
        print(f"  {arm:16s} exec_acc={ex/n:.3f}  program_match={st/n:.3f}")

    print("\n===== INCREMENTAL: past experience on top of each grounding =====")
    # 2×3 因子：grounding{fulldoc(baseline), structured} × experience{none, case, strategy, both}
    for base, exps in [("baseline", ["fulldoc_case", "fulldoc_strategy", "fulldoc_both"]),
                       ("structured", ["struct_case", "struct_strategy", "struct_both"])]:
        for arm in exps:
            delta = unified[arm]["exec"] - unified[base]["exec"]
            print(f"  {arm} vs {base}: exec {delta:+.3f}  program {unified[arm]['program']-unified[base]['program']:+.3f}")

    print("\n===== Complementarity within each grounding (exec) =====")
    allarms = config.UNIFIED_ARMS
    best_fixed = max(unified[a]["exec"] for a in allarms)
    best_arm = max(allarms, key=lambda a: unified[a]["exec"])
    per = {}
    for qid in ids:
        per[qid] = {a: finqa_exec(outs["unified"][a].get(qid, ""), dev[qid]["table"], dev[qid]["qa"]["exe_ans"]) for a in allarms}
    for base, exp_map in [("baseline", {"case": "fulldoc_case", "strategy": "fulldoc_strategy", "both": "fulldoc_both"}),
                          ("structured", {"case": "struct_case", "strategy": "struct_strategy", "both": "struct_both"})]:
        fam = [base] + list(exp_map.values())
        con = collections.Counter()
        for qid in per:
            con[(per[qid][exp_map["case"]], per[qid][exp_map["strategy"]])] += 1
        co = sum(1 for q in per if per[q][exp_map["case"]] and not per[q][exp_map["strategy"]])
        so = sum(1 for q in per if per[q][exp_map["strategy"]] and not per[q][exp_map["case"]])
        bo = sum(1 for q in per if per[q][exp_map["both"]] and not per[q][exp_map["case"]] and not per[q][exp_map["strategy"]])
        bw = sum(1 for q in per if not per[q][exp_map["both"]] and (per[q][exp_map["case"]] or per[q][exp_map["strategy"]]))
        orc = sum(any(per[q][a] for a in fam) for q in per) / n
        bf = max(unified[a]["exec"] for a in fam)
        print(f"  [{base}] contingency(case,strategy)={ {str(k): v for k, v in con.items()} }")
        print(f"      case_only={co} strategy_only={so} both_wrong_but_single={bw} both_right_singles_wrong={bo}")
        print(f"      best_fixed_in_family={bf:.3f} oracle_in_family={orc:.3f} oracle_gap={orc-bf:+.3f}")

    oracle_all = sum(any(per[q][a] for a in allarms) for q in per) / n
    print(f"\n  Best Fixed (all unified arms) = {best_fixed:.3f} ({best_arm})")
    print(f"  Oracle (all unified arms) = {oracle_all:.3f}  Gap = {oracle_all - best_fixed:+.3f}")

    # by bucket (unified)
    print("\n===== by bucket (unified exec) =====")
    cats = {c["id"]: c for c in json.load(open("/home/tiantian/keyan/analysis/cat.json"))}
    import finqa_common as fc
    buckets = collections.defaultdict(list)
    for qid in ids:
        cat = cats.get(qid)
        if not cat:
            continue
        struct = cat["struct"]
        b = fc.bucket({
            "uses_greater": "greater" in struct,
            "uses_table_op": any(o.startswith("table_") for o in struct),
            "uses_const": "const_" in (dev[qid]["qa"]["program"] or ""),
            "nstep": len(struct),
        })
        buckets[b].append(qid)
    for b, qs in sorted(buckets.items()):
        if len(qs) < 3:
            continue
        row = {a: round(sum(finqa_exec(outs["unified"][a].get(q, ""), dev[q]["table"], dev[q]["qa"]["exe_ans"]) for q in qs)/len(qs), 3) for a in allarms}
        print(f"  {b:26s} n={len(qs):3d} {row}")

    # save
    summary = {"n": n, "repro": repro, "unified": unified,
               "best_fixed": best_fixed, "best_arm": best_arm, "oracle_all": oracle_all}
    json.dump(summary, open(os.path.join(config.OUT, "evaluation.json"), "w"), indent=1)
    print("\nsaved evaluation.json")

if __name__ == "__main__":
    main()
