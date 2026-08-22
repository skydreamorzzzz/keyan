import json, os, shutil, tempfile, unittest
from pathlib import Path
from pipeline.common import ARTIFACT_ROOT, file_ref, load_json, write_json
from pipeline.case_memory import validate_cases

class CaseMemoryTests(unittest.TestCase):
    def setUp(self): self.tmp=Path(tempfile.mkdtemp()); self.root=self.tmp/"a"; self.root.mkdir(); [((self.root/p.relative_to(ARTIFACT_ROOT)).mkdir(exist_ok=True) if p.is_dir() else os.symlink(p,self.root/p.relative_to(ARTIFACT_ROOT))) for p in ARTIFACT_ROOT.rglob("*")]
    def tearDown(self): shutil.rmtree(self.tmp)
    def mutate(self, fn):
        rel=Path("memory/case_v1.jsonl"); target=self.root/rel; target.unlink(); rows=[json.loads(x) for x in (ARTIFACT_ROOT/rel).read_text().splitlines()]; fn(rows); target.write_text("\n".join(json.dumps(x,separators=(",",":")) for x in rows)+"\n"); m=self.root/"memory/case_v1.manifest.json"; m.unlink(); d=load_json(ARTIFACT_ROOT/"memory/case_v1.manifest.json"); d["records"]=file_ref(target,self.root); write_json(m,d)
    def test_identity_and_program_tampering_fail(self):
        self.mutate(lambda r:r[0].update(source_id="wrong",gold_program="add(1, 1)")); self.assertTrue(validate_cases(self.root))
    def test_hash_evidence_trace_and_coverage_fail(self):
        self.mutate(lambda r:(r[0].update(source_hash="bad",evidence=[{"evidence_id":"x","text":"not raw"}]),r[1]["reasoning_trace"][0].update(program_args=["#9","1"]),r.pop())); self.assertTrue(validate_cases(self.root))
    def test_percentage_const_and_reference_cases_validate(self):
        self.assertEqual(validate_cases(self.root),[])
if __name__=="__main__": unittest.main()
