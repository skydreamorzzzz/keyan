"""Single canonical integrity gate. It prints only the required verdict."""
import argparse, importlib.util, json, sys, contextlib, io
from pathlib import Path
import numpy as np
from pipeline.common import ROOT, ARTIFACT_ROOT, load_json, read_jsonl, sha256_file, sha256_json, sha256_bytes
from pipeline.programs import parse_strict, answers_equal

def fail(errors, message): errors.append(message)
def official_module():
    spec=importlib.util.spec_from_file_location("official",ROOT/"analysis/official_code/evaluate.py"); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def validate(root):
    errors=[]
    try:
        lock=load_json(root/"dataset_lock.json"); srcm=load_json(root/"source_pool.manifest.json"); tgtm=load_json(root/"target_pool.manifest.json")
        for split, entry in lock["raw_files"].items():
            path=ROOT/entry["path"]
            if not path.exists() or sha256_file(path) != entry["sha256"]: fail(errors,"dataset checksum: "+split)
        source=read_jsonl(root/"source_pool.jsonl"); target=read_jsonl(root/"target_pool.jsonl")
        if sha256_json(source)!=srcm["source_pool_hash"]: fail(errors,"source pool stale")
        if sha256_json(target)!=tgtm["target_pool_hash"]: fail(errors,"target pool stale")
        ids=[x["source_id"] for x in source]; tids=[x["target_id"] for x in target]
        if len(ids)!=len(set(ids)) or len(tids)!=len(set(tids)) or set(ids)&set(tids): fail(errors,"split/unique identity integrity")
        if any("shared_source_ids" in x["raw"] for x in target): fail(errors,"target contains retrieval state")
        for row in source:
            if row["source_hash"] != sha256_json(row["raw"]): fail(errors,"source hash: "+row["source_id"])
        for row in target:
            if row["target_hash"] != sha256_json(row["raw"]): fail(errors,"target hash: "+row["target_id"])
        gold=read_jsonl(root/"gold_validation.jsonl")
        expected=sum(x["count"] for x in lock["raw_files"].values())
        if len(gold)!=expected or any(not (x["parse_ok"] and x["official_ok"] and x["answer_ok"] and x.get("custom_official_match")) for x in gold): fail(errors,"gold strict parse/execution/custom-official differential")
        # Differential re-executes a deterministic sample against the bundled official evaluator.
        m=official_module()
        for row in source[:20]+target[:20]:
            raw=row["raw"]; parse_strict(raw["qa"]["program"])
            invalid,value=m.eval_program(m.program_tokenization(raw["qa"]["program"]),raw["table"])
            if invalid or not answers_equal(value,raw["qa"]["exe_ans"]): fail(errors,"official differential: "+raw["id"]); break
        repm=load_json(root/"representations/case_v1.manifest.json"); rep=read_jsonl(root/"representations/case_v1.jsonl")
        if repm["source_pool_hash"]!=srcm["source_pool_hash"] or len(rep)!=len(source) or {x["source_id"] for x in rep} != set(ids): fail(errors,"representation coverage/stale")
        emm=load_json(root/"embeddings/source_question.manifest.json"); emb=read_jsonl(root/"embeddings/source_question.jsonl"); config=load_json(ROOT/"configs/finqa_v1.json")
        if emm["source_pool_hash"]!=srcm["source_pool_hash"] or emm["embedding_config"]!=config["embedding"]: fail(errors,"embedding stale/config drift")
        if len(emb)!=len(source) or {x["source_id"] for x in emb} != set(ids): fail(errors,"embedding ID coverage")
        source_by_id={x["source_id"]:x for x in source}
        for e in emb:
            raw=source_by_id.get(e["source_id"])
            if not raw or raw["source_hash"]!=e["source_hash"] or e["embedding_text_hash"]!=sha256_bytes(raw["raw"]["qa"]["question"].encode()) or not e["vector"]: fail(errors,"embedding alignment: "+e["source_id"]); break
        rmeta=load_json(root/"retrieval/manifest.meta.json"); retrieval=read_jsonl(root/"retrieval/manifest.jsonl")
        if rmeta["source_pool_hash"]!=srcm["source_pool_hash"] or rmeta["target_pool_hash"]!=tgtm["target_pool_hash"] or rmeta["embedding_manifest_hash"]!=sha256_json(emm): fail(errors,"retrieval stale")
        if len(retrieval)!=len(target) or {x["target_id"] for x in retrieval} != set(tids): fail(errors,"retrieval coverage")
        # Exact score recomputation detects reordered/misaligned vectors without any index map.
        mat=np.asarray([x["vector"] for x in emb],dtype=float); emb_ids=[x["source_id"] for x in emb]; qmap={x["target_id"]:x for x in target}; topk=rmeta["retrieval_config"]["top_k"]
        from sentence_transformers import SentenceTransformer
        # The public gate's stdout is reserved for the verdict line.
        with contextlib.redirect_stdout(io.StringIO()):
            model=SentenceTransformer(config["embedding"]["model"],local_files_only=True)
        for row in retrieval[:min(25,len(retrieval))]:
            q=model.encode(qmap[row["target_id"]]["raw"]["qa"]["question"],normalize_embeddings=True,convert_to_numpy=True); scores=mat@q; expected=np.argsort(-scores)[:topk]
            if [n["source_id"] for n in row["neighbors"]] != [emb_ids[i] for i in expected] or any(abs(n["score"]-float(scores[i]))>1e-5 for n,i in zip(row["neighbors"],expected)): fail(errors,"retrieval score recomputation: "+row["target_id"]); break
    except Exception as exc: fail(errors,type(exc).__name__+": "+str(exc))
    return errors

if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("--artifacts",default=str(ARTIFACT_ROOT)); p.add_argument("--details",action="store_true"); a=p.parse_args(); errors=validate(Path(a.artifacts))
    if a.details:
        print(json.dumps({"errors":errors,"valid":not errors},indent=2))
    print("CANONICAL DATASET: VALID" if not errors else "CANONICAL DATASET: INVALID")
    raise SystemExit(bool(errors))
