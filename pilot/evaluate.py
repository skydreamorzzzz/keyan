"""评估：官方执行/结构指标、contingency、Best Fixed、Oracle、Oracle Gap、归因。"""
import json, os, sys, collections
import config
import finqa_common as fc
from executor import exec_program_re, match_result, canonical_re

ARMS = ["no", "case", "strategy", "both"]

def main():
    dev = {x["id"]: x for x in json.load(open(os.path.join(config.DATA_DIR, "dev.json")))}
    sample = json.load(open(os.path.join(config.OUT_DIR, "dev_sample.json")))
    ids = sample["ids"]
    outs = json.load(open(os.path.join(config.OUT_DIR, "arm_outputs.json")))

    # gold strategy family per query (from struct)
    strat_by_id = {s["strategy_id"]: s for s in json.load(open(os.path.join(config.OUT_DIR, "strategies.json")))}
    strat_by_struct = collections.defaultdict(list)
    for sid, s in strat_by_id.items():
        strat_by_struct[tuple(s.get("source_struct") or [])].append(sid)
    case_struct = {}

    per = {}
    for qid in ids:
        x = dev[qid]
        gold_re = x["qa"]["program_re"]
        gold_ans = x["qa"]["exe_ans"]
        gold_struct = tuple(sample["cat"][qid]["struct"])
        gold_canon = canonical_re(gold_re)
        rec = {
            "id": qid, "bucket": sample["meta"][qid],
            "question": x["qa"]["question"], "gold_program_re": gold_re,
            "gold_exe_ans": gold_ans, "gold_struct": list(gold_struct),
            "n_steps": len(gold_struct),
            "unit_scaling": "const_" in gold_re,
            "yesno": gold_ans in ("yes", "no"),
            "company": fc.company_of(qid),
        }
        # per arm
        for arm in ARMS:
            raw = outs[arm][qid]["raw"]
            okp, res = exec_program_re(raw, x["table"])
            exe_correct = okp and match_result(res, gold_ans)
            # official-style: round to 5 exact
            exe_off = False
            if okp and isinstance(res, (int, float)) and not isinstance(gold_ans, str):
                exe_off = round(res, 5) == round(float(gold_ans), 5)
                if gold_ans in ("yes", "no"):
                    exe_off = res == gold_ans
            pred_canon = canonical_re(normalize_for_canon(raw))
            struct_match = (pred_canon is not None and pred_canon == gold_canon)
            rec[arm] = {"exe_correct": exe_correct, "exe_off": exe_off,
                        "struct_match": struct_match, "raw": raw}
        # retrieval info from any arm (same retrieval used across arms)
        rc = outs["case"][qid]["retrieved_cases"]
        rs = outs["case"][qid]["retrieved_strategies"]
        rec["retrieved_case_ids"] = [r["id"] for r in rc]
        rec["retrieved_strategy_ids"] = [r["id"] for r in rs]
        rec["strategy_family_retrieved"] = any(r["id"] in strat_by_struct[gold_struct] for r in rs)
        per[qid] = rec

    # compute company_in_train properly
    train_companies = set(json.load(open(os.path.join(config.OUT_DIR, "case_memory.json")))[i]["company"] for i in range(len(json.load(open(os.path.join(config.OUT_DIR, "case_memory.json"))))))
    for qid in per:
        per[qid]["company_in_train"] = per[qid]["company"] in train_companies

    # case_same_struct_retrieved needs train case structs
    case_mem = json.load(open(os.path.join(config.OUT_DIR, "case_memory.json")))
    case_struct_map = {c["case_id"]: tuple(c["struct"]) for c in case_mem}
    for qid in per:
        per[qid]["case_same_struct_retrieved"] = any(
            case_struct_map.get(rid) == tuple(per[qid]["gold_struct"]) for rid in per[qid]["retrieved_case_ids"])

    # ---- metrics ----
    n = len(ids)
    acc = {arm: sum(per[q][arm]["exe_correct"] for q in per) / n for arm in ARMS}
    acc_off = {arm: sum(per[q][arm]["exe_off"] for q in per) / n for arm in ARMS}
    struct_acc = {arm: sum(per[q][arm]["struct_match"] for q in per) / n for arm in ARMS}
    parse_fail = {arm: sum(1 for q in per if per[q][arm]["exe_correct"] is False and _parse_ok(per[q][arm]["raw"]) is False) for arm in ARMS}

    best_fixed = max(acc.values())
    oracle = sum(any(per[q][a]["exe_correct"] for a in ARMS) for q in per) / n
    oracle_gap = oracle - best_fixed

    # contingency
    con = collections.Counter()
    for q in per:
        c = per[q]["case"]["exe_correct"]; s = per[q]["strategy"]["exe_correct"]
        con[(c, s)] += 1
    both_correct = con[(True, True)]
    case_only = con[(True, False)]
    strategy_only = con[(False, True)]
    neither = con[(False, False)]

    # interference: both arm wrong but case or strategy right
    inter_neg = sum(1 for q in per if not per[q]["both"]["exe_correct"] and
                    (per[q]["case"]["exe_correct"] or per[q]["strategy"]["exe_correct"]))
    inter_pos = sum(1 for q in per if per[q]["both"]["exe_correct"] and
                    not per[q]["case"]["exe_correct"] and not per[q]["strategy"]["exe_correct"])

    summary = {
        "n": n,
        "acc": {k: round(v, 4) for k, v in acc.items()},
        "acc_official_round5": {k: round(v, 4) for k, v in acc_off.items()},
        "struct_match_acc": {k: round(v, 4) for k, v in struct_acc.items()},
        "best_fixed": round(best_fixed, 4), "best_fixed_arm": max(acc, key=acc.get),
        "oracle": round(oracle, 4), "oracle_gap": round(oracle_gap, 4),
        "contingency": {"both_correct": both_correct, "case_only": case_only,
                        "strategy_only": strategy_only, "neither": neither},
        "interference": {"both_wrong_but_single_right": inter_neg, "both_right_but_singles_wrong": inter_pos},
    }
    print("=== SUMMARY ===")
    print(json.dumps(summary, indent=1, ensure_ascii=False))

    # error attribution by bucket
    print("\n=== by bucket (acc) ===")
    for b in ["A_comparison_yesno", "B_table_aggregation", "C_unitscaling_multi", "D_multistep4plus", "E_3step", "F_2step", "G_1step"]:
        qs = [q for q in per if per[q]["bucket"] == b]
        if not qs: continue
        a = {arm: round(sum(per[q][arm]["exe_correct"] for q in qs) / len(qs), 3) for arm in ARMS}
        o = round(sum(any(per[q][a2]["exe_correct"] for a2 in ARMS) for q in qs) / len(qs), 3)
        print(f"  {b:24s} n={len(qs):3d} {a} oracle={o}")

    # by dimensions
    print("\n=== by dimension (exec acc) ===")
    for dim in ["unit_scaling", "yesno"]:
        for val in [True, False]:
            qs = [q for q in per if per[q][dim] == val]
            a = {arm: round(sum(per[q][arm]["exe_correct"] for q in qs) / len(qs), 3) for arm in ARMS}
            print(f"  {dim}={val}: n={len(qs)} {a}")
    for lo, hi in [(1, 1), (2, 2), (3, 3), (4, 99)]:
        qs = [q for q in per if lo <= per[q]["n_steps"] <= hi]
        a = {arm: round(sum(per[q][arm]["exe_correct"] for q in qs) / len(qs), 3) for arm in ARMS}
        print(f"  n_steps {lo}-{hi}: n={len(qs)} {a}")

    # retrieval-conditioned
    print("\n=== strategy retrieval conditioned ===")
    for cond in [True, False]:
        qs = [q for q in per if per[q]["strategy_family_retrieved"] == cond]
        a = {arm: round(sum(per[q][arm]["exe_correct"] for q in qs) / len(qs), 3) for arm in ARMS}
        o = round(sum(any(per[q][a2]["exe_correct"] for a2 in ARMS) for q in qs) / len(qs), 3)
        print(f"  strat_family_retrieved={cond}: n={len(qs)} {a} oracle={o}")
    print("\n=== case retrieval conditioned ===")
    for cond in [True, False]:
        qs = [q for q in per if per[q]["case_same_struct_retrieved"] == cond]
        a = {arm: round(sum(per[q][arm]["exe_correct"] for q in qs) / len(qs), 3) for arm in ARMS}
        o = round(sum(any(per[q][a2]["exe_correct"] for a2 in ARMS) for q in qs) / len(qs), 3)
        print(f"  case_same_struct_retrieved={cond}: n={len(qs)} {a} oracle={o}")

    # failure cases: case_only and strategy_only
    print("\n=== Case-only correct, Strategy wrong ===")
    for q in per:
        if per[q]["case"]["exe_correct"] and not per[q]["strategy"]["exe_correct"]:
            print(f"  {q} [{per[q]['bucket']}] {per[q]['question'][:80]}")
    print("\n=== Strategy-only correct, Case wrong ===")
    for q in per:
        if not per[q]["case"]["exe_correct"] and per[q]["strategy"]["exe_correct"]:
            print(f"  {q} [{per[q]['bucket']}] {per[q]['question'][:80]}")

    # save
    out_path = os.path.join(config.OUT_DIR, "evaluation.json")
    json.dump({"summary": summary, "per_question": {k: {kk: vv for kk, vv in v.items() if kk != "raw"}
                                                    for k, v in per.items()}},
              open(out_path, "w"), indent=1, ensure_ascii=False)
    # failure detail (with raws)
    json.dump(per, open(os.path.join(config.OUT_DIR, "per_question_full.json"), "w"), indent=1, ensure_ascii=False)
    print(f"\nsaved evaluation.json + per_question_full.json")

def normalize_for_canon(raw):
    from executor import normalize_program
    n = normalize_program(raw)
    return n[len("LINEAR:"):] if n.startswith("LINEAR:") else n

def _parse_ok(raw):
    from executor import normalize_program, parse_program_re, parse_linear_steps
    n = normalize_program(raw)
    try:
        if n.startswith("LINEAR:"):
            parse_linear_steps(n[len("LINEAR:"):]); return True
        parse_program_re(n); return True
    except Exception:
        return False

if __name__ == "__main__":
    main()
