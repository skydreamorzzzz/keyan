"""official-aligned 评估：
- ff 臂：官方 Corrected exact/close（gold=qa.answer）
- prog 臂：FinQA exec（gold=exe_ans）
- 核心现象：FullDoc 族与 Structured 族的 case gain/strategy gain/case-only/strategy-only/干扰/Best Fixed/Oracle/Gap
"""
import json, os, sys, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import s2o_common as c
from executor import exec_program_re, match_result

def main():
    dev = json.load(open(os.path.join(c.DATA, "dev.json")))[:492]
    outs = json.load(open(os.path.join(c.OUT, "arm_outputs.json")))
    n = len(dev)

    print(f"n={n}\n===== REPRODUCTION (官方 Corrected Exact/Close, free-form) =====")
    repro = {}
    for arm in ["baseline", "rag", "structured", "mem0aug"]:
        ex = cl = 0
        for i in range(n):
            raw = outs["ff"].get(arm, {}).get(str(i), "")
            gold = dev[i]["qa"].get("answer", "")
            q = dev[i]["qa"]["question"]
            ex += c.exact_match(raw, gold, q)
            cl += c.numeric_close(raw, gold, q)
        repro[arm] = (ex / n, cl / n)
        print(f"  {arm:10s} exact={ex/n:.3f} close={cl/n:.3f}")

    print("\n===== FF arms (官方 Corrected Close) =====")
    ff = {}
    for arm in ["baseline", "baseline_case", "baseline_strategy", "baseline_both",
                "structured", "structured_case", "structured_strategy", "structured_both"]:
        cl = sum(c.numeric_close(outs["ff"].get(arm, {}).get(str(i), ""), dev[i]["qa"].get("answer", ""), dev[i]["qa"]["question"]) for i in range(n)) / n
        ff[arm] = cl
        print(f"  {arm:22s} close={cl:.3f}")

    print("\n===== PROG arms (FinQA exec) =====")
    prog = {}
    for arm in ["baseline", "baseline_case", "baseline_strategy", "baseline_both",
                "structured", "structured_case", "structured_strategy", "structured_both"]:
        ex = sum(1 for i in range(n) if (lambda raw: exec_program_re(raw, dev[i]["table"])[0] and match_result(exec_program_re(raw, dev[i]["table"])[1], dev[i]["qa"]["exe_ans"]))(outs["prog"].get(arm, {}).get(str(i), ""))) / n
        prog[arm] = ex
        print(f"  {arm:22s} exec={ex:.3f}")

    def phenomena(family, metric):
        if family == "baseline":
            base, case, strat, both = "baseline", "baseline_case", "baseline_strategy", "baseline_both"
        else:
            base, case, strat, both = "structured", "structured_case", "structured_strategy", "structured_both"
        per = {}
        for i in range(n):
            per[i] = {
                "base": metric(base, i), "case": metric(case, i),
                "strat": metric(strat, i), "both": metric(both, i),
            }
        case_gain = sum(per[i]["case"] for i in per) / n - sum(per[i]["base"] for i in per) / n
        strat_gain = sum(per[i]["strat"] for i in per) / n - sum(per[i]["base"] for i in per) / n
        co = sum(1 for i in per if per[i]["case"] and not per[i]["strat"])
        so = sum(1 for i in per if per[i]["strat"] and not per[i]["case"])
        bo = sum(1 for i in per if per[i]["both"] and not per[i]["case"] and not per[i]["strat"])
        bw = sum(1 for i in per if not per[i]["both"] and (per[i]["case"] or per[i]["strat"]))
        best = max(sum(per[i][a] for i in per) / n for a in ["base", "case", "strat", "both"])
        orc = sum(any(per[i][a] for a in ["base", "case", "strat", "both"]) for i in per) / n
        print(f"\n  [{family} family] base_acc={sum(per[i]['base'] for i in per)/n:.3f}")
        print(f"    case_gain={case_gain:+.3f}  strat_gain={strat_gain:+.3f}")
        print(f"    case_only={co}  strategy_only={so}  both_wrong_but_single={bw}  both_right_singles_wrong={bo}")
        print(f"    best_fixed={best:.3f}  oracle={orc:.3f}  oracle_gap={orc-best:+.3f}")

    print("\n===== CORE PHENOMENA (official Corrected Close) =====")
    def m_close(arm, i):
        return c.numeric_close(outs["ff"].get(arm, {}).get(str(i), ""), dev[i]["qa"].get("answer", ""), dev[i]["qa"]["question"])
    phenomena("baseline", m_close)
    phenomena("structured", m_close)

    print("\n===== CORE PHENOMENA (FinQA exec) =====")
    def m_exec(arm, i):
        okp, res = exec_program_re(outs["prog"].get(arm, {}).get(str(i), ""), dev[i]["table"])
        return okp and match_result(res, dev[i]["qa"]["exe_ans"])
    phenomena("baseline", m_exec)
    phenomena("structured", m_exec)

    summary = {"n": n, "repro": repro, "ff": ff, "prog": prog}
    json.dump(summary, open(os.path.join(c.OUT, "evaluation.json"), "w"), indent=1)
    print("\nsaved evaluation.json")

if __name__ == "__main__":
    main()
