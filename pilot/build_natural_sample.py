"""自然分布 dev 样本：250 条纯随机，固定种子，不按 bucket 调配。记录与分层 143 的重叠。"""
import json, os, random
import config
import finqa_common as fc

N = 250
SEED = 20260817

def main():
    dev = json.load(open(os.path.join(config.DATA_DIR, "dev.json")))
    cat = {x["id"]: fc.compute_cat(x) for x in dev}
    from collections import defaultdict
    buckets = defaultdict(int)
    rng = random.Random(SEED)
    pool = [x["id"] for x in dev]
    rng.shuffle(pool)
    ids = pool[:N]

    for cid in ids:
        buckets[fc.bucket(cat[cid])] += 1
    print("natural sample bucket dist (dev-typical, no manual weighting):")
    for b in sorted(buckets):
        print(f"  {b}: {buckets[b]}")

    strat = json.load(open(os.path.join(config.OUT_DIR, "dev_sample.json")))
    strat_ids = set(strat["ids"])
    overlap = len(set(ids) & strat_ids)
    print(f"natural n={len(ids)}, overlap with stratified 143 = {overlap} ({100*overlap/len(ids):.1f}% of natural)")

    out = {
        "ids": ids,
        "cat": {cid: cat[cid] for cid in ids},
        "meta": {cid: fc.bucket(cat[cid]) for cid in ids},
    }
    path = os.path.join(config.OUT_DIR, "dev_sample_natural.json")
    json.dump(out, open(path, "w"), ensure_ascii=False)
    print("saved", path)

if __name__ == "__main__":
    main()
