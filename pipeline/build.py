"""Build immutable FinQA v1 pools, ID-keyed embeddings, and frozen retrieval."""
import argparse, importlib.util, sys
import numpy as np
from sentence_transformers import SentenceTransformer
from pipeline.common import ROOT, ARTIFACT_ROOT, load_json, write_json, write_jsonl, sha256_file, sha256_json, sha256_bytes
from pipeline.programs import parse_strict, execute_custom, answers_equal

RAW = ROOT / "data" / "finqa"

def official_module():
    spec = importlib.util.spec_from_file_location("finqa_official", ROOT / "analysis" / "official_code" / "evaluate.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def validate_gold(items, official):
    rows=[]
    for item in items:
        qa=item["qa"]; row={"item_id": item["id"], "parse_ok": False, "official_ok": False, "answer_ok": False}
        try:
            parse_strict(qa["program"]); row["parse_ok"] = True
            invalid, result=official.eval_program(official.program_tokenization(qa["program"]), item["table"])
            row["official_result"] = result; row["official_ok"] = invalid == 0
            custom=execute_custom(qa["program"], item["table"]); row["custom_result"] = custom
            row["custom_official_match"] = row["official_ok"] and answers_equal(custom,result)
            row["answer_ok"] = row["official_ok"] and answers_equal(result, qa["exe_ans"])
        except Exception as error: row["error"] = type(error).__name__ + ": " + str(error)
        rows.append(row)
    return rows

def identity_record(item, split):
    # Entire raw item is retained verbatim; identity hash binds every raw field.
    return {"source_id": item["id"], "source_hash": sha256_json(item), "split": split, "raw": item}

def build(args):
    config=load_json(ROOT / args.config); ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    raw_by_split={s: load_json(RAW/(s+".json")) for s in ("train","dev","test")}
    lock={"schema_version": config["schema_version"], "raw_files": {s: {"path": str((RAW/(s+".json")).relative_to(ROOT)), "sha256": sha256_file(RAW/(s+".json")), "count": len(v)} for s,v in raw_by_split.items()}}
    lock["lock_hash"] = sha256_json(lock); write_json(ARTIFACT_ROOT/"dataset_lock.json",lock)
    all_items=[item for vals in raw_by_split.values() for item in vals]
    official=official_module(); gold=validate_gold(all_items,official); write_jsonl(ARTIFACT_ROOT/"gold_validation.jsonl",gold)
    source=[identity_record(x,"train") for x in raw_by_split["train"]]
    target=[{"target_id":x["id"],"target_hash":sha256_json(x),"split":split,"raw":x} for split in config["splits"]["target"] for x in raw_by_split[split]]
    source_manifest={"kind":"source_pool","schema_version":config["schema_version"],"dataset_lock_hash":lock["lock_hash"],"count":len(source),"source_pool_hash":sha256_json(source),"records":"source_pool.jsonl"}
    target_manifest={"kind":"target_pool","schema_version":config["schema_version"],"dataset_lock_hash":lock["lock_hash"],"count":len(target),"target_pool_hash":sha256_json(target),"records":"target_pool.jsonl"}
    write_jsonl(ARTIFACT_ROOT/"source_pool.jsonl",source); write_jsonl(ARTIFACT_ROOT/"target_pool.jsonl",target); write_json(ARTIFACT_ROOT/"source_pool.manifest.json",source_manifest); write_json(ARTIFACT_ROOT/"target_pool.manifest.json",target_manifest)
    # Case is a deterministic raw-grounded representation. Other representations are intentionally absent until separately versioned/QC'd.
    case=[{"source_id":r["source_id"],"source_hash":r["source_hash"],"representation":"case_v1","text":r["raw"]["qa"]["question"],"representation_hash":sha256_json({"source_id":r["source_id"],"question":r["raw"]["qa"]["question"]})} for r in source]
    rep={"kind":"memory_representation","representation":"case_v1","status":"VALID","source_pool_hash":source_manifest["source_pool_hash"],"count":len(case),"records":"representations/case_v1.jsonl"}
    write_jsonl(ARTIFACT_ROOT/"representations/case_v1.jsonl",case); write_json(ARTIFACT_ROOT/"representations/case_v1.manifest.json",rep)
    if args.until == "pools": return
    embcfg=config["embedding"]; model=SentenceTransformer(embcfg["model"], local_files_only=True)
    texts=[r["raw"]["qa"]["question"] for r in source]; vectors=model.encode(texts, batch_size=embcfg["batch_size"], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=True)
    embeddings=[]
    for r,text,vector in zip(source,texts,vectors): embeddings.append({"source_id":r["source_id"],"source_hash":r["source_hash"],"embedding_model":embcfg["model"],"model_revision":embcfg["revision"],"embedding_text_hash":sha256_bytes(text.encode()),"vector":vector.astype(float).tolist()})
    em={"kind":"id_keyed_embeddings","source_pool_hash":source_manifest["source_pool_hash"],"embedding_config":embcfg,"count":len(embeddings),"records":"embeddings/source_question.jsonl"}
    write_jsonl(ARTIFACT_ROOT/"embeddings/source_question.jsonl",embeddings); write_json(ARTIFACT_ROOT/"embeddings/source_question.manifest.json",em)
    if args.until == "embeddings": return
    target_texts=[r["raw"]["qa"]["question"] for r in target]; qvec=model.encode(target_texts,batch_size=embcfg["batch_size"],normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=True)
    matrix=np.asarray(vectors); k=config["retrieval"]["top_k"]; rows=[]
    for t,q in zip(target,qvec):
        scores=matrix @ q; idx=np.argsort(-scores)[:k]
        rows.append({"target_id":t["target_id"],"target_hash":t["target_hash"],"query_text_hash":sha256_bytes(t["raw"]["qa"]["question"].encode()),"neighbors":[{"source_id":embeddings[i]["source_id"],"source_hash":embeddings[i]["source_hash"],"score":float(scores[i])} for i in idx]})
    rm={"kind":"frozen_retrieval_manifest","source_pool_hash":source_manifest["source_pool_hash"],"target_pool_hash":target_manifest["target_pool_hash"],"embedding_manifest_hash":sha256_json(em),"retrieval_config":config["retrieval"],"count":len(rows),"records":"retrieval/manifest.jsonl"}
    write_jsonl(ARTIFACT_ROOT/"retrieval/manifest.jsonl",rows); write_json(ARTIFACT_ROOT/"retrieval/manifest.meta.json",rm)

if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("--config",default="configs/finqa_v1.json"); p.add_argument("--until",choices=["pools","embeddings","retrieval"],default="retrieval"); build(p.parse_args())
