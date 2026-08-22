import json, os, shutil, tempfile, unittest
from unittest.mock import patch
from pathlib import Path
from pipeline.common import ROOT, ARTIFACT_ROOT, load_json, sha256_file
from pipeline.build import checked_raw, build
from pipeline.programs import ProgramError, parse_strict
from pipeline.evaluator import evaluate_strict
from pipeline.validate import validate, verify_ref

class CanonicalV11Tests(unittest.TestCase):
    def setUp(self): self.tmp=Path(tempfile.mkdtemp())
    def tearDown(self): shutil.rmtree(self.tmp)
    def test_strict_rejects_forward_and_malformed(self):
        with self.assertRaises(ProgramError): parse_strict("add(#0, 1)")
        self.assertFalse(evaluate_strict("add(1 2)",3,[])["valid_program"])
    def test_frozen_lock_rejects_changed_raw_byte(self):
        lock=load_json(ROOT/"configs/finqa_v1_upstream_lock.json"); altered=dict(lock); altered["raw_files"]=dict(lock["raw_files"]); altered["raw_files"]["train"]=dict(lock["raw_files"]["train"]); altered["raw_files"]["train"]["sha256"]="0"*64
        with self.assertRaisesRegex(RuntimeError,"UPSTREAM LOCK FAILURE"): checked_raw(altered)
    def test_build_fails_closed_before_artifact_creation(self):
        out=self.tmp/"never-published"
        with patch("pipeline.build.checked_raw",side_effect=RuntimeError("UPSTREAM LOCK FAILURE")):
            with self.assertRaisesRegex(RuntimeError,"UPSTREAM LOCK FAILURE"): build(artifacts=out)
        self.assertFalse(out.exists())
    def test_byte_hash_detects_pool_embedding_and_retrieval_tampering(self):
        for rel in ("source_pool.jsonl","targets/dev_pool.jsonl","embeddings/source_question.jsonl","retrieval/dev_manifest.jsonl"):
            manifest_rel={"source_pool.jsonl":"source_pool.manifest.json","targets/dev_pool.jsonl":"targets/dev_pool.manifest.json","embeddings/source_question.jsonl":"embeddings/source_question.manifest.json","retrieval/dev_manifest.jsonl":"retrieval/dev_manifest.manifest.json"}[rel]
            manifest=load_json(ARTIFACT_ROOT/manifest_rel); changed=self.tmp/rel; changed.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ARTIFACT_ROOT/rel,changed)
            rows=changed.read_text().splitlines(); row=json.loads(rows[0])
            if rel == "source_pool.jsonl": row["source_hash"]="tampered"
            elif rel == "targets/dev_pool.jsonl": row["target_hash"]="tampered"
            elif rel == "embeddings/source_question.jsonl": row["vector"][0] += 1.0
            else: row["neighbors"][0]["source_id"]="tampered-id"
            rows[0]=json.dumps(row,separators=(",",":")); changed.write_text("\n".join(rows)+"\n")
            errors=[]; verify_ref(self.tmp,manifest["records"],rel,errors); self.assertTrue(errors,rel)
    def test_dev_test_identity_is_disjoint(self):
        with open(ARTIFACT_ROOT/"targets/dev_pool.jsonl") as handle: dev={json.loads(x)["target_id"] for x in handle if x.strip()}
        with open(ARTIFACT_ROOT/"targets/test_pool.jsonl") as handle: test={json.loads(x)["target_id"] for x in handle if x.strip()}
        self.assertFalse(dev & test)
    def test_full_retrieval_recomputation_reaches_last_dev_row(self):
        # A symlinked artifact view lets us alter only the final record without duplicating 119 MB.
        root=self.tmp/"a"; root.mkdir()
        for path in ARTIFACT_ROOT.rglob("*"):
            dest=root/path.relative_to(ARTIFACT_ROOT)
            if path.is_dir(): dest.mkdir(exist_ok=True)
            else: os.symlink(path,dest)
        rel=Path("retrieval/dev_manifest.jsonl"); target=root/rel; target.unlink(); rows=(ARTIFACT_ROOT/rel).read_text().splitlines(); last=json.loads(rows[-1]); last["neighbors"][0]["source_id"]="tampered-id"; rows[-1]=json.dumps(last,separators=(",",":")); target.write_text("\n".join(rows)+"\n")
        errors=validate(root)
        self.assertTrue(any("dev retrieval topk: "+last["target_id"] in x for x in errors),errors[:10])

if __name__ == "__main__": unittest.main()
