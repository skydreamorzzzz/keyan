"""失败案例详查：输出 case_only / strategy_only / 干扰案例的完整上下文，供报告分析。"""
import json, os
import config
import finqa_common as fc

def main():
    per = json.load(open(os.path.join(config.OUT_DIR, "per_question_full.json")))
    case_mem = {c["case_id"]: c for c in json.load(open(os.path.join(config.OUT_DIR, "case_memory.json")))}
    strat_by_id = {s["strategy_id"]: s for s in json.load(open(os.path.join(config.OUT_DIR, "strategies.json")))}

    lines = []
    def dump(qid, tag):
        p = per[qid]
        lines.append("=" * 100)
        lines.append(f"[{tag}] {qid}  bucket={p['bucket']} n_steps={p['n_steps']} unit_scaling={p['unit_scaling']}")
        lines.append(f"Q: {p['question']}")
        lines.append(f"GOLD: {p['gold_program_re']}  ans={p['gold_exe_ans']}")
        for arm in ["no", "case", "strategy", "both"]:
            ok = p[arm]["exe_correct"]
            lines.append(f"  {arm:8s} correct={ok!s:5s} raw={p[arm]['raw'][:150]!r}")
        rc = p.get("retrieved_case_ids", [])
        lines.append("  retrieved cases:")
        for cid in rc[:3]:
            c = case_mem.get(cid, {})
            lines.append(f"    {cid} [{c.get('problem_kind')}] Q:{c.get('question','')[:80]}")
            lines.append(f"       prog={c.get('program_re','')[:80]}")
        rs = p.get("retrieved_strategy_ids", [])
        lines.append("  retrieved strategies:")
        for sid in rs[:3]:
            s = strat_by_id.get(sid, {})
            lines.append(f"    {sid} {s.get('name')} | {s.get('template')}")
        lines.append("")

    for qid, p in per.items():
        c = p["case"]["exe_correct"]; s = p["strategy"]["exe_correct"]
        if c and not s:
            dump(qid, "case_only")
    for qid, p in per.items():
        c = p["case"]["exe_correct"]; s = p["strategy"]["exe_correct"]
        if (not c) and s:
            dump(qid, "strategy_only")
    for qid, p in per.items():
        if (not p["both"]["exe_correct"]) and (p["case"]["exe_correct"] or p["strategy"]["exe_correct"]):
            dump(qid, "interference_both_worse")

    out = os.path.join(config.OUT_DIR, "failure_cases.txt")
    open(out, "w").write("\n".join(lines))
    print(f"saved {out} ({len(lines)} lines)")

if __name__ == "__main__":
    main()
