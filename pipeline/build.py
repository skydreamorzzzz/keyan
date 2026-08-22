"""Fail-closed, atomic builder for Canonical FinQA Pipeline v1.1."""
import argparse, contextlib, importlib.util, io, os, shutil, tempfile
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer
import sentence_transformers
from pipeline.common import ROOT, ARTIFACT_ROOT, load_json, read_jsonl, write_json, write_jsonl, sha256_file, sha256_json, sha256_bytes, file_ref
from pipeline.programs import parse_strict, execute_custom, primary_answers_equal

def official_module():
    spec=importlib.util.spec_from_file_location("finqa_official",ROOT/"analysis/official_code/evaluate.py"); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def checked_raw(lock):
    data={}
    for split, expected in lock["raw_files"].items():
        path=ROOT/expected["path"]
        if not path.is_file() or sha256_file(path)!=expected["sha256"]: raise RuntimeError("UPSTREAM LOCK FAILURE: "+split)
        rows=load_json(path)
        if len(rows)!=expected["count"]: raise RuntimeError("UPSTREAM COUNT FAILURE: "+split)
        data[split]=rows
    return data

def gold_rows(raw, official):
    rows=[]; failures=[]
    for split, items in raw.items():
        for item in items:
            qa=item["qa"]; row={"item_id":item["id"],"split":split}
            try:
                parse_strict(qa["program"])
                invalid, official_answer=official.eval_program(official.program_tokenization(qa["program"]),item["table"])
                custom_answer=execute_custom(qa["program"],item["table"])
                row.update({"parse_ok":True,"official_ok":invalid==0,"official_result":official_answer,"custom_result":custom_answer,"exe_ans_ok":invalid==0 and primary_answers_equal(official_answer,qa["exe_ans"]),"custom_official_match":invalid==0 and primary_answers_equal(custom_answer,official_answer)})
            except Exception as exc: row.update({"parse_ok":False,"official_ok":False,"exe_ans_ok":False,"custom_official_match":False,"error":type(exc).__name__})
            if not all(row.get(k) for k in ("parse_ok","official_ok","exe_ans_ok","custom_official_match")): failures.append(item["id"])
            rows.append(row)
    if failures: raise RuntimeError("GOLD GATE FAILURE: "+",".join(failures[:20]))
    return rows

def source_record(item): return {"source_id":item["id"],"source_hash":sha256_json(item),"split":"train","raw":item}
def target_record(item, split, purpose): return {"target_id":item["id"],"target_hash":sha256_json(item),"split":split,"purpose":purpose,"raw":item}

def manifest(kind, root, records, parents, **fields):
    result={"kind":kind,"records":file_ref(records,root),"parents":parents}; result.update(fields); return result

def build(config_path="configs/finqa_v1.json", artifacts=ARTIFACT_ROOT):
    config_path=ROOT/config_path if not Path(config_path).is_absolute() else Path(config_path); config=load_json(config_path)
    lock_path=ROOT/config["upstream_lock"]; lock=load_json(lock_path)
    raw=checked_raw(lock) # Gate 1: no output mutation before immutable raw verification.
    official=official_module(); gold=gold_rows(raw,official) # Gate 2: full strict/official/custom check.
    artifacts=Path(artifacts); temp=Path(tempfile.mkdtemp(prefix="finqa_v1_",dir=artifacts.parent)); backup=None
    try:
        write_json(temp/"dataset_lock.json",lock)
        lock_ref=file_ref(temp/"dataset_lock.json",temp); config_ref={"path":str(config_path.relative_to(ROOT)),"sha256":sha256_file(config_path)}
        write_jsonl(temp/"gold_validation.jsonl",gold)
        gold_m=manifest("gold_validation",temp,temp/"gold_validation.jsonl",{"dataset_lock":lock_ref,"official_evaluator_sha256":sha256_file(ROOT/"analysis/official_code/evaluate.py"),"custom_executor_sha256":sha256_file(ROOT/"pipeline/programs.py")},count=len(gold),config=config_ref); write_json(temp/"gold_validation.manifest.json",gold_m)
        source=[source_record(x) for x in raw[config["source_split"]]]
        if len({x["source_id"] for x in source})!=len(source): raise RuntimeError("POOL GATE FAILURE: duplicate source IDs")
        write_jsonl(temp/"source_pool.jsonl",source); source_m=manifest("immutable_source_pool",temp,temp/"source_pool.jsonl",{"dataset_lock":lock_ref,"gold_validation":file_ref(temp/"gold_validation.manifest.json",temp)},count=len(source),config=config_ref); write_json(temp/"source_pool.manifest.json",source_m)
        target_ms={}; targets={}
        for split,purpose in config["target_splits"].items():
            rows=[target_record(x,split,purpose) for x in raw[split]]; targets[split]=rows
            if set(x["source_id"] for x in source)&set(x["target_id"] for x in rows): raise RuntimeError("POOL GATE FAILURE: source/target overlap")
            write_jsonl(temp/f"targets/{split}_pool.jsonl",rows); m=manifest("immutable_target_pool",temp,temp/f"targets/{split}_pool.jsonl",{"dataset_lock":lock_ref,"gold_validation":file_ref(temp/"gold_validation.manifest.json",temp)},split=split,purpose=purpose,count=len(rows),config=config_ref); write_json(temp/f"targets/{split}_pool.manifest.json",m); target_ms[split]=m
        if set(x["target_id"] for x in targets["dev"])&set(x["target_id"] for x in targets["test"]): raise RuntimeError("POOL GATE FAILURE: dev/test overlap")
        retrieval_text=[{"source_id":r["source_id"],"source_hash":r["source_hash"],"representation":"retrieval_question_v1","text":r["raw"]["qa"][config["embedding"]["text_field"]],"text_hash":sha256_bytes(r["raw"]["qa"][config["embedding"]["text_field"]].encode())} for r in source]
        write_jsonl(temp/"representations/retrieval_question_v1.jsonl",retrieval_text); rep_m=manifest("retrieval_text_representation",temp,temp/"representations/retrieval_question_v1.jsonl",{"source_pool":file_ref(temp/"source_pool.manifest.json",temp)},count=len(retrieval_text),representation="retrieval_question_v1",status="VALID",config=config_ref); write_json(temp/"representations/retrieval_question_v1.manifest.json",rep_m)
        embcfg=config["embedding"]
        with contextlib.redirect_stdout(io.StringIO()): model=SentenceTransformer(embcfg["model"],revision=embcfg["revision"],local_files_only=True,device="cpu")
        texts=[r["text"] for r in retrieval_text]; vectors=model.encode(texts,batch_size=embcfg["batch_size"],normalize_embeddings=embcfg["normalize_embeddings"],convert_to_numpy=True,show_progress_bar=False)
        if len(vectors)!=len(source) or not np.isfinite(vectors).all(): raise RuntimeError("EMBEDDING GATE FAILURE")
        emb=[{"source_id":r["source_id"],"source_hash":r["source_hash"],"embedding_text_hash":r["text_hash"],"vector":v.astype(float).tolist()} for r,v in zip(retrieval_text,vectors)]
        write_jsonl(temp/"embeddings/source_question.jsonl",emb); em_m=manifest("id_keyed_embeddings",temp,temp/"embeddings/source_question.jsonl",{"source_pool":file_ref(temp/"source_pool.manifest.json",temp),"retrieval_text":file_ref(temp/"representations/retrieval_question_v1.manifest.json",temp)},count=len(emb),model=embcfg["model"],model_revision=embcfg["revision"],sentence_transformers_version=sentence_transformers.__version__,vector_dimension=int(vectors.shape[1]),normalization=embcfg["normalize_embeddings"],text_field=embcfg["text_field"],config=config_ref); write_json(temp/"embeddings/source_question.manifest.json",em_m)
        # Read the serialized ledger back: retrieval is bound to artifact bytes, not an in-memory array.
        emb=read_jsonl(temp/"embeddings/source_question.jsonl"); matrix=np.asarray([x["vector"] for x in emb],dtype=float); k=config["retrieval"]["top_k"]; decimals=config["retrieval"]["score_decimals"]; source_ids=np.asarray([x["source_id"] for x in emb])
        if k<=0 or k>len(source): raise RuntimeError("RETRIEVAL GATE FAILURE: top_k")
        for split, target in targets.items():
            qtexts=[r["raw"]["qa"][config["retrieval"]["query_field"]] for r in target]; qvec=model.encode(qtexts,batch_size=embcfg["batch_size"],normalize_embeddings=embcfg["normalize_embeddings"],convert_to_numpy=True,show_progress_bar=False); all_scores=np.round(qvec @ matrix.T,decimals); rows=[]
            for t,scores in zip(target,all_scores):
                ids=np.lexsort((source_ids,-scores))[:k]
                rows.append({"target_id":t["target_id"],"target_hash":t["target_hash"],"query_text_hash":sha256_bytes(t["raw"]["qa"][config["retrieval"]["query_field"]].encode()),"neighbors":[{"source_id":emb[i]["source_id"],"source_hash":emb[i]["source_hash"],"score":float(scores[i])} for i in ids]})
            write_jsonl(temp/f"retrieval/{split}_manifest.jsonl",rows); rm=manifest("frozen_retrieval_manifest",temp,temp/f"retrieval/{split}_manifest.jsonl",{"embedding":file_ref(temp/"embeddings/source_question.manifest.json",temp),"target_pool":file_ref(temp/f"targets/{split}_pool.manifest.json",temp)},split=split,purpose=config["target_splits"][split],count=len(rows),retrieval_config=config["retrieval"],config=config_ref); write_json(temp/f"retrieval/{split}_manifest.manifest.json",rm)
        # Gate 3/4: independently validate the staged tree before atomic publish.
        from pipeline.validate import validate
        # Reuse the frozen loaded model, but still perform a second full encode from representation text.
        errors=validate(temp,config_path=config_path,model=model,release=False)
        if errors: raise RuntimeError("STAGED VALIDATION FAILURE: "+"; ".join(errors[:10]))
        if artifacts.exists(): backup=artifacts.with_name(artifacts.name+".previous"); shutil.rmtree(backup,ignore_errors=True); os.replace(artifacts,backup)
        os.replace(temp,artifacts); temp=None
        if backup: shutil.rmtree(backup)
    except Exception:
        if backup and backup.exists() and not artifacts.exists(): os.replace(backup,artifacts)
        raise
    finally:
        if temp and temp.exists(): shutil.rmtree(temp)

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--config",default="configs/finqa_v1.json"); p.add_argument("--artifacts",default=str(ARTIFACT_ROOT)); a=p.parse_args(); build(a.config,a.artifacts)
