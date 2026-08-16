"""Clean Oracle 评估：双样本、6 臂、Oracle/contingency/interference/retrieval-conditioned/scale-tolerant。"""
import json, os, collections, re
import config
import finqa_common as fc
from executor import exec_program_re, match_result, canonical_re, normalize_program

ARMS = ["no", "case_all", "case_cc", "strategy", "both_all", "both_cc"]
SINGLES = ["no", "case_all", "case_cc", "strategy"]

def percent_ish(question, gold_struct):
    q = question.lower()
    kw = any(w in q for w in ["percent", "%", "growth", "ratio", "portion", "share", "change",
                              "increase", "decrease", "return"])
    div_end = bool(gold_struct) and gold_struct[-1] == "divide"
    return kw and div_end

def main():
    dev = {x["id"]: x for x in json.load(open(os.path.join(config.DATA_DIR, "dev.json")))}
    case_mem = json.load(open(os.path.join(config.OUT_DIR, "case_memory.json")))
    case_struct = {c["case_id"]: tuple(c["struct"]) for c in case_mem}
    strat_by_id = {s["strategy_id"]: s for s in json.load(open(os.path.join(config.OUT_DIR, "strategies_clean.json")))}
    strat_fam = {s["strategy_id"]: [tuple(f) for f in s["program_family"]] for s in strat_by_id.values()}
    outs = json.load(open(os.path.join(config.OUT_DIR, "arm_outputs_clean.json")))

    report = {}
    for tag in ["strat", "nat"]:
        sample = json.load(open(os.path.join(config.OUT_DIR, "dev_sample.json" if tag == "strat" else "dev_sample_natural.json")))
        ids = sample["ids"]
        n = len(ids)

        per = {}
        for qid in ids:
            x = dev[qid]
            gold_re = x["qa"]["program_re"]
            gold_ans = x["qa"]["exe_ans"]
            gs = tuple(sample["cat"][qid]["struct"])
            rec = {"id": qid, "bucket": sample["meta"][qid], "question": x["qa"]["question"],
                   "gold_program_re": gold_re, "gold_exe_ans": gold_ans, "gold_struct": list(gs),
                   "n_steps": len(gs), "unit_scaling": "const_" in gold_re,
                   "yesno": gold_ans in ("yes", "no"), "company": fc.company_of(qid),
                   "percent_ish": percent_ish(x["qa"]["question"], gs)}
            # per arm
            for arm in ARMS:
                v = outs[tag][arm].get(qid)
                if not v:
                    rec[arm] = {"exe_correct": False, "scale_ok": False, "struct_match": False, "raw": ""}
                    continue
                raw = v["raw"]
                okp, res = exec_program_re(raw, x["table"])
                exe_correct = okp and match_result(res, gold_ans)
                # scale-tolerant (percentage family): accept x1/x100/div100
                scale_ok = exe_correct
                if not scale_ok and okp and isinstance(res, (int, float)) and not isinstance(gold_ans, str):
                    if rec["percent_ish"]:
                        g = float(gold_ans)
                        scale_ok = any(abs(res * f - g) <= max(1e-3, 1e-3*abs(g)) for f in (1, 100, 0.01))
                pc = canonical_re(normalize_program(raw))
                struct_match = pc is not None and pc == canonical_re(gold_re)
                rec[arm] = {"exe_correct": exe_correct, "scale_ok": scale_ok,
                            "struct_match": struct_match, "raw": raw}
            # retrieval info (from case_all arm's recorded retrieval)
            rc = outs[tag]["case_all"].get(qid, {}).get("retrieved_cases", [])
            rs = outs[tag]["strategy"].get(qid, {}).get("retrieved_strategies", [])
            rec["retrieved_case_ids"] = [r["id"] for r in rc]
            rec["retrieved_strategy_ids"] = [r["id"] for r in rs]
            rec["n_same_company_cases"] = sum(1 for cid in rec["retrieved_case_ids"] if fc.company_of(cid) == rec["company"])
            rec["case_same_struct_hit"] = any(case_struct.get(cid) == gs for cid in rec["retrieved_case_ids"])
            rec["strategy_family_hit"] = any(sid in strat_fam and gs in strat_fam[sid] for sid in rec["retrieved_strategy_ids"])
            per[qid] = rec

        def acc(arm, key="exe_correct"):
            return sum(per[q][arm][key] for q in per) / n

        # core metrics
        accs = {arm: acc(arm) for arm in ARMS}
        accs_scale = {arm: acc(arm, "scale_ok") for arm in ARMS}
        accs_struct = {arm: acc(arm, "struct_match") for arm in ARMS}
        best_fixed = max(accs.values()); best_arm = max(accs, key=accs.get)
        oracle = sum(any(per[q][a]["exe_correct"] for a in ARMS) for q in per) / n
        oracle_gap = oracle - best_fixed

        # contingency (case_all vs strategy)
        con = collections.Counter()
        for q in per:
            con[(per[q]["case_all"]["exe_correct"], per[q]["strategy"]["exe_correct"])] += 1
        # contingency with case_cc
        con_cc = collections.Counter()
        for q in per:
            con_cc[(per[q]["case_cc"]["exe_correct"], per[q]["strategy"]["exe_correct"])] += 1

        inter = collections.Counter()
        for q in per:
            c = per[q]["case_all"]["exe_correct"]; s = per[q]["strategy"]["exe_correct"]
            b = per[q]["both_all"]["exe_correct"]
            inter["both_worse"] += (not b) and (c or s)
            inter["both_better"] += b and (not c) and (not s)
            inter["both_same"] += b == max(c, s)

        # by bucket
        bucket_acc = {}
        for b in ["A_comparison_yesno","B_table_aggregation","C_unitscaling_multi","D_multistep4plus","E_3step","F_2step","G_1step"]:
            qs = [q for q in per if per[q]["bucket"] == b]
            if not qs: continue
            bucket_acc[b] = {a: round(sum(per[q][a]["exe_correct"] for q in qs)/len(qs), 3) for a in ARMS}
            bucket_acc[b]["n"] = len(qs)
            bucket_acc[b]["oracle"] = round(sum(any(per[q][a]["exe_correct"] for a in ARMS) for q in qs)/len(qs), 3)

        # retrieval conditioned
        retc = {}
        for cond_key, key in [("strategy_family_hit", "strategy"), ("case_same_struct_hit", "case_all")]:
            for cond in [True, False]:
                qs = [q for q in per if per[q][cond_key] == cond]
                retc[f"{cond_key}={cond}"] = {a: round(sum(per[q][a]["exe_correct"] for q in qs)/len(qs), 3) for a in ARMS}
                retc[f"{cond_key}={cond}"]["n"] = len(qs)

        # cross-company effect
        qs_sc = [q for q in per if per[q]["n_same_company_cases"] > 0]
        qs_nc = [q for q in per if per[q]["n_same_company_cases"] == 0]
        xcomp = {
            "with_same_company_in_top4": {"n": len(qs_sc),
                "case_all": round(sum(per[q]["case_all"]["exe_correct"] for q in qs_sc)/max(len(qs_sc),1),3),
                "case_cc": round(sum(per[q]["case_cc"]["exe_correct"] for q in qs_sc)/max(len(qs_sc),1),3)},
            "no_same_company_in_top4": {"n": len(qs_nc),
                "case_all": round(sum(per[q]["case_all"]["exe_correct"] for q in qs_nc)/max(len(qs_nc),1),3),
                "case_cc": round(sum(per[q]["case_cc"]["exe_correct"] for q in qs_nc)/max(len(qs_nc),1),3)},
            "mean_same_company_cases": round(sum(per[q]["n_same_company_cases"] for q in per)/n, 2),
        }

        def key2str(k):
            return "TT" if k == (True, True) else "TF" if k == (True, False) else "FT" if k == (False, True) else "FF"
        summary = {
            "n": n, "acc": {k: round(v, 4) for k, v in accs.items()},
            "acc_scale_tolerant": {k: round(v, 4) for k, v in accs_scale.items()},
            "acc_struct": {k: round(v, 4) for k, v in accs_struct.items()},
            "best_fixed": round(best_fixed, 4), "best_arm": best_arm,
            "oracle": round(oracle, 4), "oracle_gap": round(oracle_gap, 4),
            "contingency_case_all_vs_strategy": {key2str(k): v for k, v in con.items()},
            "contingency_case_cc_vs_strategy": {key2str(k): v for k, v in con_cc.items()},
            "interference_both_all": dict(inter),
            "retrieval_conditioned": retc,
            "cross_company": xcomp,
        }
        report[tag] = {"summary": summary, "bucket": bucket_acc, "per_question": per}

        # print
        print(f"===== {tag} (n={n}) =====")
        print("acc:", json.dumps(summary["acc"]))
        print(f"best_fixed={summary['best_fixed']} ({summary['best_arm']})  oracle={summary['oracle']}  gap={summary['oracle_gap']}")
        print("contingency(case_all,strategy):", dict(con))
        print("contingency(case_cc,strategy):", dict(con_cc))
        print("interference both_all:", dict(inter))
        print("retrieval-cond:", json.dumps(retc, ensure_ascii=False))
        print("cross-company:", json.dumps(xcomp, ensure_ascii=False))
        print("bucket:")
        for b, v in bucket_acc.items():
            print(f"  {b:24s} n={v['n']:3d} { {a: v[a] for a in ARMS} } oracle={v['oracle']}")

    # save
    path = os.path.join(config.OUT_DIR, "evaluation_clean.json")
    # per_question 不含 raw，单独存
    slim = {tag: {"summary": report[tag]["summary"], "bucket": report[tag]["bucket"],
                  "per_question": {k: {kk: vv for kk, vv in v.items() if kk != "raw"} for k, v in report[tag]["per_question"].items()}}
            for tag in report}
    json.dump(slim, open(path, "w"), indent=1, ensure_ascii=False)
    # full with raw
    json.dump(report, open(os.path.join(config.OUT_DIR, "per_question_clean_full.json"), "w"), indent=1, ensure_ascii=False)
    print("saved evaluation_clean.json + per_question_clean_full.json")

if __name__ == "__main__":
    main()
