"""Clean Oracle 失败案例详查：case-only / strategy-only / 干扰 / cross-company 差异。"""
import json, os
import config
import finqa_common as fc

def main():
    report = json.load(open(os.path.join(config.OUT_DIR, "per_question_clean_full.json")))
    case_mem = {c["case_id"]: c for c in json.load(open(os.path.join(config.OUT_DIR, "case_memory.json")))}
    strat_by_id = {s["strategy_id"]: s for s in json.load(open(os.path.join(config.OUT_DIR, "strategies_clean.json")))}

    lines = []
    def dump(per, qid, tag, note=""):
        p = per[qid]
        lines.append("=" * 100)
        lines.append(f"[{tag}] {qid}  bucket={p['bucket']} unit_scaling={p['unit_scaling']} {note}")
        lines.append(f"Q: {p['question']}")
        lines.append(f"GOLD: {p['gold_program_re']}  ans={p['gold_exe_ans']}")
        for arm in ["no", "case_all", "case_cc", "strategy", "both_all", "both_cc"]:
            lines.append(f"  {arm:9s} correct={p[arm]['exe_correct']!s:5s} raw={p[arm]['raw'][:130]!r}")
        for cid in p.get("retrieved_case_ids", [])[:3]:
            c = case_mem.get(cid, {})
            lines.append(f"    case {cid} [{c.get('problem_kind')}] {c.get('question','')[:70]} | {c.get('program_re','')[:60]}")
        for sid in p.get("retrieved_strategy_ids", [])[:3]:
            s = strat_by_id.get(sid, {})
            lines.append(f"    strat {sid} {s.get('name')} | {s.get('template')}")
        lines.append("")

    for tag in ["strat", "nat"]:
        per = report[tag]["per_question"]
        lines.append(f"\n############ {tag} ############")
        for qid, p in per.items():
            c = p["case_all"]["exe_correct"]; s = p["strategy"]["exe_correct"]
            if c and not s: dump(per, qid, "case_only")
        for qid, p in per.items():
            c = p["case_all"]["exe_correct"]; s = p["strategy"]["exe_correct"]
            if (not c) and s: dump(per, qid, "strategy_only")
        for qid, p in per.items():
            if (not p["both_all"]["exe_correct"]) and (p["case_all"]["exe_correct"] or p["strategy"]["exe_correct"]):
                dump(per, qid, "interference_both_all")
        for qid, p in per.items():
            if p["case_all"]["exe_correct"] and not p["case_cc"]["exe_correct"]:
                dump(per, qid, "xcomp_case_all_win")
            elif p["case_cc"]["exe_correct"] and not p["case_all"]["exe_correct"]:
                dump(per, qid, "xcomp_case_cc_win")

    out = os.path.join(config.OUT_DIR, "failure_cases_clean.txt")
    open(out, "w").write("\n".join(lines))
    print(f"saved {out} ({len(lines)} lines)")

if __name__ == "__main__":
    main()
