"""检索 sanity check：抽查 dev query，保存 query/retrieved case/strategy/score/gold program，供人工判断。"""
import json, os, random
import config
import finqa_common as fc
import retrieval
from executor import parse_linear_steps

def main():
    dev = {x["id"]: x for x in json.load(open(os.path.join(config.DATA_DIR, "dev.json")))}
    sample = json.load(open(os.path.join(config.OUT_DIR, "dev_sample.json")))
    ids = sample["ids"]
    cases = {c["case_id"]: c for c in json.load(open(os.path.join(config.OUT_DIR, "case_memory.json")))}
    strategies = {s["strategy_id"]: s for s in json.load(open(os.path.join(config.OUT_DIR, "strategies.json")))}

    rng = random.Random(7)
    check_ids = rng.sample(ids, min(config.RETRIEVAL_CHECK_N, len(ids)))

    out = []
    for cid in check_ids:
        x = dev[cid]
        q = x["qa"]["question"]
        rc = retrieval.retrieve_cases(q, exclude_company=x["id"].split("/")[0])
        rs = retrieval.retrieve_strategies(q)
        rec = {
            "query_id": cid,
            "query": q,
            "gold_program": x["qa"]["program_re"],
            "bucket": sample["meta"].get(cid),
            "retrieved_cases": [{"id": r["case_id"], "score": round(r["score"], 4),
                                 "question": cases[r["case_id"]]["question"],
                                 "program_re": cases[r["case_id"]]["program_re"],
                                 "problem_kind": cases[r["case_id"]]["problem_kind"]} for r in rc],
            "retrieved_strategies": [{"id": r["strategy_id"], "score": round(r["score"], 4),
                                      "name": strategies[r["strategy_id"]]["name"],
                                      "type": strategies[r["strategy_id"]]["problem_type"],
                                      "template": strategies[r["strategy_id"]]["template"]} for r in rs],
            "judgment_case": "",   # 人工填写
            "judgment_strategy": "",
        }
        out.append(rec)

    path = os.path.join(config.OUT_DIR, "retrieval_check.json")
    json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
    print(f"retrieval check saved: {path} ({len(out)} queries)")

if __name__ == "__main__":
    main()
