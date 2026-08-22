"""Fail-closed release gate; default stdout is exactly one verdict line."""
import argparse, contextlib, importlib.util, io, json, math
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer
from pipeline.common import ROOT, ARTIFACT_ROOT, load_json, read_jsonl, sha256_file, sha256_bytes, file_ref
from pipeline.programs import parse_strict, execute_custom, primary_answers_equal

def official_module():
    spec=importlib.util.spec_from_file_location("official",ROOT/"analysis/official_code/evaluate.py"); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def add(errors,msg): errors.append(msg)
def verify_ref(root, ref, label, errors):
    try:
        path=root/ref["path"]
        if not path.is_file() or file_ref(path,root)!={k:ref[k] for k in ("path","sha256","bytes")}: add(errors,"byte hash: "+label)
    except Exception: add(errors,"invalid reference: "+label)
def verify_config(manifest, config_ref, label, errors):
    if manifest.get("config") != config_ref: add(errors,"config provenance: "+label)
def live_gold_row(split, item, official):
    qa=item["qa"]; row={"item_id":item["id"],"split":split}
    try:
        parse_strict(qa["program"]); invalid,off=official.eval_program(official.program_tokenization(qa["program"]),item["table"]); custom=execute_custom(qa["program"],item["table"])
        row.update({"parse_ok":True,"official_ok":invalid==0,"official_result":off,"custom_result":custom,"exe_ans_ok":invalid==0 and primary_answers_equal(off,qa["exe_ans"]),"custom_official_match":invalid==0 and primary_answers_equal(custom,off)})
    except Exception as exc: row.update({"parse_ok":False,"official_ok":False,"exe_ans_ok":False,"custom_official_match":False,"error":type(exc).__name__})
    return row
def gold_rows_equal(cached, live):
    for key in ("split","item_id","parse_ok","official_ok","exe_ans_ok","custom_official_match","error"):
        if cached.get(key) != live.get(key): return False
    for key in ("official_result","custom_result"):
        if key in cached or key in live:
            if cached.get(key) != live.get(key): return False
    return True

def validate(root=ARTIFACT_ROOT, config_path=ROOT/"configs/finqa_v1.json", model=None, release=True):
    root=Path(root); config_path=Path(config_path); errors=[]
    try:
        config=load_json(config_path); config_ref={"path":str(config_path.relative_to(ROOT)),"sha256":sha256_file(config_path)}; frozen=load_json(ROOT/config["upstream_lock"]); lock=load_json(root/"dataset_lock.json")
        if lock!=frozen: add(errors,"dataset lock is not frozen upstream lock")
        lock_ref=file_ref(root/"dataset_lock.json",root)
        raw={}
        for split, expected in frozen["raw_files"].items():
            path=ROOT/expected["path"]
            if not path.is_file() or sha256_file(path)!=expected["sha256"]: add(errors,"dataset checksum: "+split); continue
            raw[split]=load_json(path)
            if len(raw[split])!=expected["count"]: add(errors,"dataset count: "+split)
        gold_m=load_json(root/"gold_validation.manifest.json"); verify_config(gold_m,config_ref,"gold",errors); verify_ref(root,gold_m["records"],"gold records",errors); verify_ref(root,gold_m["parents"]["dataset_lock"],"gold lock parent",errors)
        if gold_m["parents"].get("official_evaluator_sha256")!=sha256_file(ROOT/"analysis/official_code/evaluate.py") or gold_m["parents"].get("custom_executor_sha256")!=sha256_file(ROOT/"pipeline/programs.py"): add(errors,"gold evaluator provenance")
        # Do not trust cache: full live strict parser + official + custom differential.
        live_gold={}
        if release:
            official=official_module()
            for split, items in raw.items():
                for item in items:
                    result=live_gold_row(split,item,official); live_gold[(split,item["id"])]=result
                    if not all(result.get(k) for k in ("parse_ok","official_ok","exe_ans_ok","custom_official_match")): add(errors,"gold execution/differential: "+item["id"])
        cached=read_jsonl(root/gold_m["records"]["path"])
        cached_by_id={(x.get("split"),x.get("item_id")):x for x in cached}
        expected_gold_keys={(split,x["id"]) for split,items in raw.items() for x in items}
        if len(cached)!=len(expected_gold_keys) or set(cached_by_id)!=expected_gold_keys: add(errors,"gold cache coverage")
        if release:
            for key, live in live_gold.items():
                if not gold_rows_equal(cached_by_id.get(key,{}),live): add(errors,"gold cache/live mismatch: "+key[1])
        source_m=load_json(root/"source_pool.manifest.json"); verify_config(source_m,config_ref,"source",errors); verify_ref(root,source_m["records"],"source records",errors); verify_ref(root,source_m["parents"]["dataset_lock"],"source lock parent",errors); verify_ref(root,source_m["parents"]["gold_validation"],"source gold parent",errors)
        source=read_jsonl(root/source_m["records"]["path"]); sid={x["source_id"] for x in source}
        if len(sid)!=len(source) or len(source)!=source_m["count"]: add(errors,"source ID coverage")
        raw_source={x["id"]:x for x in raw[config["source_split"]]}
        for r in source:
            if r["source_hash"] != __import__('pipeline.common',fromlist=['sha256_json']).sha256_json(r["raw"]) or r["source_id"] not in raw_source or r["raw"]!=raw_source[r["source_id"]]: add(errors,"source identity: "+r["source_id"])
        targets={}; target_ms={}
        for split in config["target_splits"]:
            m=load_json(root/f"targets/{split}_pool.manifest.json"); target_ms[split]=m; verify_config(m,config_ref,split+" target",errors); verify_ref(root,m["records"],split+" target records",errors); verify_ref(root,m["parents"]["dataset_lock"],split+" lock parent",errors); verify_ref(root,m["parents"]["gold_validation"],split+" gold parent",errors)
            rows=read_jsonl(root/m["records"]["path"]); targets[split]=rows; ids={x["target_id"] for x in rows}
            if len(ids)!=len(rows) or len(rows)!=m["count"] or ids&sid or any(x["purpose"]!=config["target_splits"][split] for x in rows): add(errors,split+" target integrity")
            raw_target={x["id"]:x for x in raw[split]}
            for r in rows:
                if r["target_hash"] != __import__('pipeline.common',fromlist=['sha256_json']).sha256_json(r["raw"]) or r["target_id"] not in raw_target or r["raw"]!=raw_target[r["target_id"]] or "shared_source_ids" in r["raw"]: add(errors,split+" target identity: "+r["target_id"])
        if {x["target_id"] for x in targets["dev"]}&{x["target_id"] for x in targets["test"]}: add(errors,"dev/test identity overlap")
        repm=load_json(root/"representations/retrieval_question_v1.manifest.json"); verify_config(repm,config_ref,"retrieval text",errors); verify_ref(root,repm["records"],"retrieval text",errors); verify_ref(root,repm["parents"]["source_pool"],"representation source parent",errors); rep=read_jsonl(root/repm["records"]["path"])
        if repm["representation"]!="retrieval_question_v1" or len(rep)!=len(source) or len({x.get("source_id") for x in rep})!=len(rep) or {x.get("source_id") for x in rep}!=sid: add(errors,"retrieval text representation coverage")
        by_source={x["source_id"]:x for x in source}; by_rep={x["source_id"]:x for x in rep}; text_field=config["embedding"]["text_field"]
        for record in rep:
            source_row=by_source.get(record.get("source_id")); expected_text=source_row["raw"]["qa"].get(text_field) if source_row else None
            if not source_row or record.get("source_hash")!=source_row["source_hash"] or record.get("representation")!="retrieval_question_v1" or record.get("text")!=expected_text or record.get("text_hash")!=sha256_bytes(str(record.get("text","")).encode()): add(errors,"retrieval text semantic identity: "+str(record.get("source_id")))
        emm=load_json(root/"embeddings/source_question.manifest.json"); verify_config(emm,config_ref,"embedding",errors); verify_ref(root,emm["records"],"embedding records",errors); verify_ref(root,emm["parents"]["source_pool"],"embedding source parent",errors); verify_ref(root,emm["parents"]["retrieval_text"],"embedding representation parent",errors); emb=read_jsonl(root/emm["records"]["path"])
        if any(emm[k]!=config["embedding"][{"model":"model","model_revision":"revision","normalization":"normalize_embeddings","text_field":"text_field"}[k]] for k in ("model","model_revision","normalization","text_field")): add(errors,"embedding config provenance")
        if len(emb)!=len(source) or {x["source_id"] for x in emb}!=sid: add(errors,"embedding ID coverage")
        for e in emb:
            s=by_source.get(e["source_id"]); r=by_rep.get(e["source_id"])
            if not s or not r or e["source_hash"]!=s["source_hash"] or e["embedding_text_hash"]!=r["text_hash"] or len(e["vector"])!=emm["vector_dimension"] or not np.isfinite(e["vector"]).all(): add(errors,"embedding identity: "+e["source_id"])
        matrix=np.asarray([e["vector"] for e in emb],dtype=float); emb_ids=[e["source_id"] for e in emb]; emb_by_id={e["source_id"]:e for e in emb}; k=config["retrieval"]["top_k"]; decimals=config["retrieval"]["score_decimals"]
        if model is None:
            with contextlib.redirect_stdout(io.StringIO()): model=SentenceTransformer(config["embedding"]["model"],revision=config["embedding"]["revision"],local_files_only=True,device="cpu")
        if release:
            # Full independent source re-encoding: identity is dictionary keyed by source_id, never matrix position.
            rep_texts=[(r["source_id"],r["text"]) for r in rep]
            fresh=model.encode([text for _,text in rep_texts],batch_size=config["embedding"]["batch_size"],normalize_embeddings=config["embedding"]["normalize_embeddings"],convert_to_numpy=True,show_progress_bar=False)
            fresh_by_id={source_id:vector for (source_id,_),vector in zip(rep_texts,fresh)}
            if len(fresh_by_id)!=len(source): add(errors,"source re-encode coverage")
            for source_id, vector in fresh_by_id.items():
                committed=np.asarray(emb_by_id[source_id]["vector"],dtype=float) if source_id in emb_by_id else None
                norm=np.linalg.norm(vector)
                if committed is None or vector.shape != committed.shape or not np.isfinite(vector).all() or (config["embedding"]["normalize_embeddings"] and not np.isclose(norm,1.0,atol=1e-5,rtol=0)) or not np.allclose(vector,committed,atol=1e-6,rtol=1e-6): add(errors,"source embedding re-encode mismatch: "+source_id)
        # Full, not sampled, recomputation independently derives every query vector and top-k.
        for split, rows in targets.items():
            rm=load_json(root/f"retrieval/{split}_manifest.manifest.json"); verify_config(rm,config_ref,split+" retrieval",errors); verify_ref(root,rm["records"],split+" retrieval records",errors); verify_ref(root,rm["parents"]["embedding"],split+" embedding parent",errors); verify_ref(root,rm["parents"]["target_pool"],split+" target parent",errors); retrieval=read_jsonl(root/rm["records"]["path"]); rmap={r["target_id"]:r for r in retrieval}
            if len(retrieval)!=len(rows) or len(rmap)!=len(rows) or set(rmap)!={x["target_id"] for x in rows}: add(errors,split+" retrieval coverage")
            if not release: continue
            queries=[x["raw"]["qa"][config["retrieval"]["query_field"]] for x in rows]; qvec=model.encode(queries,batch_size=config["embedding"]["batch_size"],normalize_embeddings=config["embedding"]["normalize_embeddings"],convert_to_numpy=True,show_progress_bar=False); all_scores=np.round(qvec @ matrix.T,decimals)
            for target,scores in zip(rows,all_scores):
                row=rmap.get(target["target_id"])
                if not row: continue
                expected=np.lexsort((np.asarray(emb_ids),-scores))[:k]; neighbors=row.get("neighbors",[])
                if row.get("target_hash")!=target["target_hash"] or row.get("query_text_hash")!=sha256_bytes(target["raw"]["qa"][config["retrieval"]["query_field"]].encode()) or len(neighbors)!=k or len({n.get("source_id") for n in neighbors})!=k: add(errors,split+" retrieval row: "+target["target_id"]); continue
                actual=[n["source_id"] for n in neighbors]
                if actual != [emb_ids[i] for i in expected]: add(errors,split+" retrieval topk: "+target["target_id"])
                for pos,(n,i) in enumerate(zip(neighbors,expected)):
                    if n["source_id"] not in sid or n.get("source_hash")!=emb_by_id[n["source_id"]]["source_hash"] or not math.isfinite(n.get("score",float("nan"))) or (pos and n["score"]>neighbors[pos-1]["score"]) or n["score"]!=float(scores[i]): add(errors,split+" retrieval score: "+target["target_id"]); break
    except Exception as exc: add(errors,type(exc).__name__+": "+str(exc))
    return errors

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--artifacts",default=str(ARTIFACT_ROOT)); p.add_argument("--config",default=str(ROOT/"configs/finqa_v1.json")); p.add_argument("--details",action="store_true"); a=p.parse_args(); errors=validate(a.artifacts,a.config)
    if a.details: print(json.dumps({"valid":not errors,"errors":errors},indent=2))
    print("CANONICAL DATASET: VALID" if not errors else "CANONICAL DATASET: INVALID")
    raise SystemExit(bool(errors))
