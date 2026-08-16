"""dev 分层采样（配额式）。

决策：150 条，配额偏向结构化/策略型类型（comparison/table_agg/unitscaling/长链），
理由：这些类型才是 Case/Strategy 互补性最可能有差异的地方；自然分布下单步占比过高。
后果：整体 accuracy 不等于自然分布，报告会同时给 bucket 分层结果。
"""
import json, os, random
import config
import finqa_common as fc

def main():
    dev = json.load(open(os.path.join(config.DATA_DIR, "dev.json")))
    # bucket per sample
    cat = {x["id"]: fc.compute_cat(x) for x in dev}
    from collections import defaultdict
    pools = defaultdict(list)
    for x in dev:
        pools[fc.bucket(cat[x["id"]])].append(x["id"])

    rng = random.Random(config.DEV_SEED)
    sel, meta = [], {}
    for b, quota in config.BUCKET_QUOTA.items():
        ids = pools.get(b, [])
        if not ids and quota:
            print(f"[warn] bucket {b} has 0 dev samples")
        rng.shuffle(ids)
        chosen = ids[:quota]
        for cid in chosen:
            sel.append(cid)
            meta[cid] = {"bucket": b, "cat": cat[cid]}

    print(f"sampled {len(sel)} dev samples")
    for b, quota in config.BUCKET_QUOTA.items():
        got = sum(1 for m in meta.values() if m["bucket"] == b)
        print(f"  {b}: quota={quota} got={got}")

    with open(os.path.join(config.OUT_DIR, "dev_sample.json"), "w") as f:
        json.dump({"ids": sel, "meta": {k: v["bucket"] for k, v in meta.items()},
                   "cat": {k: v["cat"] for k, v in meta.items()}}, f, ensure_ascii=False)
    print("saved dev_sample.json")

if __name__ == "__main__":
    main()
