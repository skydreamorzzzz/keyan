import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.case_memory import (CONSTRUCTOR, SCHEMA, build, validate_cases)
from pipeline.common import ARTIFACT_ROOT, file_ref, load_json, sha256_json, write_json


class CaseMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "artifact_root"
        self.root.mkdir()
        for path in ARTIFACT_ROOT.rglob("*"):
            relative = path.relative_to(ARTIFACT_ROOT)
            target = self.root / relative
            if path.is_dir():
                target.mkdir(exist_ok=True)
            else:
                os.symlink(path, target)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _mutate(self, callback, rehash_records=True):
        records_rel = Path("memory/case_v1.jsonl")
        target = self.root / records_rel
        target.unlink()
        rows = [json.loads(line) for line in (ARTIFACT_ROOT / records_rel).read_text().splitlines()]
        callback(rows)
        if rehash_records:
            for row in rows:
                row.pop("representation_hash", None)
                row["representation_hash"] = sha256_json(row)
        target.write_text("\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n")
        manifest_path = self.root / "memory/case_v1.manifest.json"
        manifest_path.unlink()
        manifest = load_json(ARTIFACT_ROOT / "memory/case_v1.manifest.json")
        manifest["records"] = file_ref(target, self.root)
        manifest["qc_failures"] = {}
        write_json(manifest_path, manifest)

    def _case_with(self, predicate):
        rows = [json.loads(line) for line in (ARTIFACT_ROOT / "memory/case_v1.jsonl").read_text().splitlines()]
        return next(index for index, row in enumerate(rows) if predicate(row))

    def test_full_case_artifact_validates(self):
        self.assertEqual(validate_cases(self.root), [])

    def test_contract_fields_fail_even_when_record_hash_is_recomputed(self):
        for field, value in (("representation_id", "case_v1:wrong"),
                             ("constructor_version", "wrong"),
                             ("parent_source_manifest", {"path": "wrong", "sha256": "x", "bytes": 0}),
                             ("qc_status", "INVALID")):
            with self.subTest(field=field):
                self._mutate(lambda rows, f=field, v=value: rows[0].update({f: v}))
                self.assertTrue(validate_cases(self.root))
                (self.root / "memory/case_v1.jsonl").unlink()
                os.symlink(ARTIFACT_ROOT / "memory/case_v1.jsonl", self.root / "memory/case_v1.jsonl")
                (self.root / "memory/case_v1.manifest.json").unlink()
                os.symlink(ARTIFACT_ROOT / "memory/case_v1.manifest.json", self.root / "memory/case_v1.manifest.json")

    def test_manifest_contract_fields_fail(self):
        for field, value in (("constructor_sha256", "bad"), ("count", 6250)):
            with self.subTest(field=field):
                manifest_path = self.root / "memory/case_v1.manifest.json"
                manifest_path.unlink()
                manifest = load_json(ARTIFACT_ROOT / "memory/case_v1.manifest.json")
                manifest[field] = value
                write_json(manifest_path, manifest)
                self.assertTrue(validate_cases(self.root))
                manifest_path.unlink()
                os.symlink(ARTIFACT_ROOT / "memory/case_v1.manifest.json", manifest_path)

    def test_grounding_and_high_risk_trace_tampering_fail_after_hash_updates(self):
        table_index = self._case_with(lambda row: row["table_grounding"])
        const_index = self._case_with(lambda row: any("const_100" in step["program_args"] for step in row["reasoning_trace"]))
        percent_index = self._case_with(lambda row: any(arg.endswith("%") for step in row["reasoning_trace"] for arg in step["program_args"]))
        reference_index = self._case_with(lambda row: any(arg.startswith("#") for step in row["reasoning_trace"] for arg in step["program_args"]))
        attacks = [
            (table_index, lambda row: row["table_grounding"][0]["raw_cells"].__setitem__(0, "999")),
            (const_index, lambda row: next(step for step in row["reasoning_trace"] if "const_100" in step["program_args"]).__setitem__("result", 999)),
            (percent_index, lambda row: next(step for step in row["reasoning_trace"] if any(arg.endswith("%") for arg in step["program_args"])).__setitem__("resolved_args", [999, 999])),
            (reference_index, lambda row: next(step for step in row["reasoning_trace"] if any(arg.startswith("#") for arg in step["program_args"])).__setitem__("program_args", ["#0", "#0"])),
        ]
        for index, attack in attacks:
            with self.subTest(index=index):
                self._mutate(lambda rows, i=index, fn=attack: fn(rows[i]))
                self.assertTrue(validate_cases(self.root))
                (self.root / "memory/case_v1.jsonl").unlink()
                os.symlink(ARTIFACT_ROOT / "memory/case_v1.jsonl", self.root / "memory/case_v1.jsonl")
                (self.root / "memory/case_v1.manifest.json").unlink()
                os.symlink(ARTIFACT_ROOT / "memory/case_v1.manifest.json", self.root / "memory/case_v1.manifest.json")

    def test_missing_and_duplicate_sources_fail(self):
        self._mutate(lambda rows: rows.pop())
        self.assertTrue(validate_cases(self.root))
        (self.root / "memory/case_v1.jsonl").unlink()
        os.symlink(ARTIFACT_ROOT / "memory/case_v1.jsonl", self.root / "memory/case_v1.jsonl")
        (self.root / "memory/case_v1.manifest.json").unlink()
        os.symlink(ARTIFACT_ROOT / "memory/case_v1.manifest.json", self.root / "memory/case_v1.manifest.json")
        self._mutate(lambda rows: rows.__setitem__(1, dict(rows[0])))
        self.assertTrue(validate_cases(self.root))

    def test_failed_or_exceptional_qc_preserves_old_memory_and_cleans_stage(self):
        root = self.tmp / "atomic_root"
        root.mkdir()
        for name in ("source_pool.manifest.json", "source_pool.jsonl"):
            os.symlink(ARTIFACT_ROOT / name, root / name)
        old_memory = root / "memory"
        old_memory.mkdir()
        (old_memory / "sentinel").write_text("old-case-artifacts")
        fake_case = lambda source, parent: {"source_id": source["source_id"]}
        for outcome in (["forced QC failure"], RuntimeError("forced validator exception")):
            with self.subTest(outcome=repr(outcome)), patch("pipeline.case_memory.case", fake_case), \
                    patch("pipeline.case_memory.validate_cases", side_effect=outcome):
                with self.assertRaises((RuntimeError, Exception)):
                    build(root)
                self.assertEqual((old_memory / "sentinel").read_text(), "old-case-artifacts")
                self.assertFalse((root / "memory.previous").exists())
                self.assertEqual(list(root.glob("case_v1_*")), [])


if __name__ == "__main__":
    unittest.main()
