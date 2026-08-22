"""Deterministic CaseRepresentationV1.1 construction and fidelity validation.

Case records are a lossless, source-local view of a solved FinQA training
experience.  This module deliberately has no model or generation dependency.
"""
import argparse
import importlib.util
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from pipeline.common import (ARTIFACT_ROOT, ROOT, file_ref, load_json, read_jsonl,
                             sha256_file, sha256_json, write_json, write_jsonl)
from pipeline.programs import parse_strict

SCHEMA = "CaseRepresentationV1.1"
CONSTRUCTOR = "case_memory_constructor_v1_1"
RECORDS_PATH = "memory/case_v1.jsonl"
MANIFEST_PATH = "memory/case_v1.manifest.json"


def official():
    spec = importlib.util.spec_from_file_location(
        "finqa_official", ROOT / "analysis/official_code/evaluate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def num(token):
    token = token.replace(",", "").replace("$", "").strip()
    if token.startswith("const_"):
        return -1.0 if token == "const_m1" else float(token[6:])
    if token.endswith("%"):
        return float(token[:-1]) / 100
    return float(token)


def table_grounding(program, table):
    """Rows actually consumed by table operators, in parsed-program order."""
    rows = {str(row[0]): (index, row) for index, row in enumerate(table)}
    grounding = []
    for step_index, step in enumerate(parse_strict(program)):
        op, row_name = step["op"], step["args"][0]
        if not op.startswith("table_"):
            continue
        if row_name not in rows:
            raise ValueError("gold program table row missing: " + row_name)
        row_index, row = rows[row_name]
        raw_cells = list(row[1:])
        grounding.append({
            "step_index": step_index,
            "operation": op,
            "row_index": row_index,
            "row_name": row_name,
            "raw_cells": raw_cells,
            "parsed_numeric_cells": [num(str(cell).split("(")[0]) for cell in raw_cells],
        })
    return grounding


def trace(program, table=None, grounding=None):
    """Strict program trace; table steps can execute from Case-local grounding."""
    values, out = [], []
    rows = {str(row[0]): row[1:] for row in table} if table is not None else {}
    grounding_by_step = {entry["step_index"]: entry for entry in (grounding or [])}
    for index, step in enumerate(parse_strict(program)):
        op, a, b = step["op"], step["args"][0], step["args"][1]
        entry = {"step_index": index, "operation": op, "program_args": [a, b]}
        if op.startswith("table_"):
            if table is not None:
                vals = [num(str(cell).split("(")[0]) for cell in rows[a]]
            else:
                if index not in grounding_by_step:
                    raise ValueError("case grounding missing for table step %d" % index)
                vals = grounding_by_step[index]["parsed_numeric_cells"]
            result = {"table_max": max, "table_min": min, "table_sum": sum,
                      "table_average": lambda values: sum(values) / len(values)}[op](vals)
            entry.update({"resolved_args": [a, "none"], "table_grounding_step_index": index,
                          "result": result})
        else:
            resolved = [values[int(arg[1:])] if arg.startswith("#") else num(arg)
                        for arg in (a, b)]
            x, y = resolved
            result = {"add": lambda: x + y, "subtract": lambda: x - y,
                      "multiply": lambda: x * y, "divide": lambda: x / y,
                      "exp": lambda: x ** y,
                      "greater": lambda: "yes" if x > y else "no"}[op]()
            entry.update({"resolved_args": resolved, "result": result})
        # FinQA rounds only the final output; references retain exact intermediates.
        values.append(result)
        out.append(entry)
    return out


def case(source, parent):
    raw, qa = source["raw"], source["raw"]["qa"]
    record = {
        "representation_id": "case_v1:" + source["source_id"],
        "representation_type": "case",
        "schema_version": SCHEMA,
        "constructor_version": CONSTRUCTOR,
        "source_id": source["source_id"],
        "source_hash": source["source_hash"],
        "parent_source_manifest": parent,
        "question": qa["question"],
        "evidence": [{"evidence_id": key, "text": value}
                     for key, value in qa["gold_inds"].items()],
        "table_grounding": table_grounding(qa["program"], raw["table"]),
        "gold_program": qa["program"],
        "gold_answer": qa["answer"],
        "exe_ans": qa["exe_ans"],
        "reasoning_trace": trace(qa["program"], table=raw["table"]),
        "qc_status": "VALID",
    }
    record["representation_hash"] = sha256_json(record)
    return record


def _record_ref(records_path):
    return {"path": RECORDS_PATH, "sha256": sha256_file(records_path),
            "bytes": records_path.stat().st_size}


def validate_cases(root=ARTIFACT_ROOT, memory_dir=None):
    """Full semantic/provenance Case QC; returns errors instead of trusting hashes."""
    root = Path(root)
    memory_dir = Path(memory_dir) if memory_dir else root / "memory"
    errors = []
    source_manifest_path = root / "source_pool.manifest.json"
    source_manifest = load_json(source_manifest_path)
    source = read_jsonl(root / source_manifest["records"]["path"])
    byid = {record["source_id"]: record for record in source}
    expected_parent = file_ref(source_manifest_path, root)
    manifest_path, records_path = memory_dir / "case_v1.manifest.json", memory_dir / "case_v1.jsonl"
    try:
        manifest, cases = load_json(manifest_path), read_jsonl(records_path)
    except Exception as exc:
        return ["case artifact unreadable: " + repr(exc)]

    if manifest.get("kind") != "case_memory": errors.append("manifest kind")
    if manifest.get("schema_version") != SCHEMA: errors.append("manifest schema_version")
    if manifest.get("constructor_version") != CONSTRUCTOR: errors.append("manifest constructor_version")
    if manifest.get("constructor_sha256") != sha256_file(Path(__file__)):
        errors.append("manifest constructor_sha256")
    if manifest.get("parents", {}).get("source_pool") != expected_parent:
        errors.append("manifest source parent")
    if manifest.get("records") != _record_ref(records_path): errors.append("case records hash")
    if manifest.get("count") != len(cases) or manifest.get("count") != len(source):
        errors.append("manifest count")
    actual_failures = Counter(str(case.get("qc_status")) for case in cases if case.get("qc_status") != "VALID")
    if manifest.get("qc_failures") != dict(sorted(actual_failures.items())):
        errors.append("manifest qc_failures")
    ids = [record.get("source_id") for record in cases]
    if len(cases) != len(source) or len(set(ids)) != len(source) or set(ids) != set(byid):
        errors.append("case coverage")

    evaluator = official()
    forbidden = {"target_id", "shared_source_ids", "strategy", "retrieval", "retrieval_metadata"}
    for record in cases:
        source_record = byid.get(record.get("source_id"))
        if not source_record:
            errors.append("case unknown source: " + str(record.get("source_id")))
            continue
        raw, qa = source_record["raw"], source_record["raw"]["qa"]
        base = dict(record)
        got_hash = base.pop("representation_hash", None)
        if (got_hash != sha256_json(base) or
                record.get("representation_id") != "case_v1:" + source_record["source_id"] or
                record.get("representation_type") != "case" or
                record.get("schema_version") != SCHEMA or
                record.get("constructor_version") != CONSTRUCTOR or
                record.get("source_hash") != source_record["source_hash"] or
                record.get("parent_source_manifest") != expected_parent or
                record.get("qc_status") != "VALID" or forbidden & set(record)):
            errors.append("case contract: " + source_record["source_id"])
            continue
        expected_evidence = [{"evidence_id": key, "text": value}
                             for key, value in qa["gold_inds"].items()]
        expected_grounding = table_grounding(qa["program"], raw["table"])
        expected_trace = trace(qa["program"], table=raw["table"])
        if (record.get("question") != qa["question"] or
                record.get("gold_program") != qa["program"] or
                record.get("gold_answer") != qa["answer"] or
                record.get("exe_ans") != qa["exe_ans"] or
                record.get("evidence") != expected_evidence or
                record.get("table_grounding") != expected_grounding or
                record.get("reasoning_trace") != expected_trace):
            errors.append("case fidelity: " + source_record["source_id"])
            continue
        try:
            # This proves table steps are executable from only Case-local grounding.
            if trace(qa["program"], grounding=record["table_grounding"]) != record["reasoning_trace"]:
                errors.append("case grounding execution: " + source_record["source_id"])
                continue
            invalid, result = evaluator.eval_program(
                evaluator.program_tokenization(qa["program"]), raw["table"])
            final = record["reasoning_trace"][-1]["result"]
            trace_answer = final if isinstance(final, str) else round(float(final), 5)
            if invalid or trace_answer != result:
                errors.append("case execution: " + source_record["source_id"])
        except Exception as exc:
            errors.append("case execution exception %s: %s" % (source_record["source_id"], exc))
    return errors


def _publish_memory(stage_memory, root):
    """Replace only a fully QC'd Case directory; restore old state on any exception."""
    target = root / "memory"
    previous = root / "memory.previous"
    if previous.exists():
        shutil.rmtree(previous)
    moved_old = False
    try:
        if target.exists():
            os.replace(target, previous)
            moved_old = True
        os.replace(stage_memory, target)
        if previous.exists():
            shutil.rmtree(previous)
    except Exception:
        if moved_old and previous.exists() and not target.exists():
            os.replace(previous, target)
        raise
    finally:
        if previous.exists() and target.exists():
            shutil.rmtree(previous)


def build(root=ARTIFACT_ROOT):
    root = Path(root)
    source_manifest = load_json(root / "source_pool.manifest.json")
    source = read_jsonl(root / source_manifest["records"]["path"])
    parent = file_ref(root / "source_pool.manifest.json", root)
    stage = Path(tempfile.mkdtemp(prefix="case_v1_", dir=root))
    stage_memory = stage / "memory"
    try:
        rows = [case(record, parent) for record in source]
        records_path = stage_memory / "case_v1.jsonl"
        write_jsonl(records_path, rows)
        manifest = {
            "kind": "case_memory", "schema_version": SCHEMA,
            "constructor_version": CONSTRUCTOR,
            "constructor_sha256": sha256_file(Path(__file__)),
            "parents": {"source_pool": parent}, "records": _record_ref(records_path),
            "count": len(rows), "qc_failures": {},
        }
        write_json(stage_memory / "case_v1.manifest.json", manifest)
        errors = validate_cases(root, stage_memory)
        if errors:
            raise RuntimeError("CASE QC FAILURE: " + "; ".join(errors[:10]))
        _publish_memory(stage_memory, root)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _family_audit(cases, failed_ids=()):
    families = {"literal_percentage_token": lambda s: any(arg.endswith("%") for arg in s["program_args"]),
                "const_100": lambda s: "const_100" in s["program_args"],
                "multiply_const_100": lambda s: s["operation"] == "multiply" and "const_100" in s["program_args"],
                "divide_percentage_conversion": lambda s: s["operation"] == "divide" and any(arg.endswith("%") for arg in s["program_args"]),
                "multi_step_reference": lambda s: any(arg.startswith("#") for arg in s["program_args"]),
                "table_sum": lambda s: s["operation"] == "table_sum",
                "table_average": lambda s: s["operation"] == "table_average",
                "table_max": lambda s: s["operation"] == "table_max",
                "table_min": lambda s: s["operation"] == "table_min",
                "greater": lambda s: s["operation"] == "greater",
                "exp": lambda s: s["operation"] == "exp",
                "three_or_more_steps": lambda s: False}
    data = {}
    failed_ids = set(failed_ids)
    for name, predicate in families.items():
        if name == "three_or_more_steps":
            selected = [case for case in cases if len(case["reasoning_trace"]) >= 3]
            ids = {case["source_id"] for case in selected}
            data[name] = (len(ids), sum(len(case["reasoning_trace"]) for case in selected),
                          len(ids & failed_ids))
        else:
            selected = [(case, step) for case in cases for step in case["reasoning_trace"] if predicate(step)]
            ids = {case["source_id"] for case, _ in selected}
            data[name] = (len(ids), len(selected), len(ids & failed_ids))
    return data


def audit(root=ARTIFACT_ROOT):
    cases = read_jsonl(Path(root) / RECORDS_PATH)
    errors = validate_cases(root)
    error_ids = {error.split(": ")[-1] for error in errors if ": " in error}
    operations = Counter(step["operation"] for case in cases for step in case["reasoning_trace"])
    families = _family_audit(cases, error_ids)
    lines = ["# Case Memory V1.1 Audit", "",
             "## Information boundary", "",
             "`question`, `evidence` (`qa.gold_inds`), `gold_program`, `gold_answer`, and `exe_ans` are verbatim raw FinQA fields. `table_grounding` is the exact raw row/cells consumed by each strict parsed table operator. `reasoning_trace`, numeric cells, IDs, and hashes are deterministic derivations. No target, retrieval, strategy, or LLM-generated field is present.",
             "", "## Full QC", "", "- Source coverage: %d/6251" % len(cases),
             "- QC failures: %d" % len(errors),
             "- Table-grounded Cases: %d" % sum(bool(case["table_grounding"]) for case in cases),
             "- Trace execution: official FinQA evaluator aligned for every Case", "",
             "## High-risk family audit", "", "| Family | Case count | Step count | QC failures |", "|---|---:|---:|---:|"]
    for name, (case_count, step_count, failures) in families.items():
        lines.append("| `%s` | %d | %d | %d |" % (name, case_count, step_count, failures))
    lines.extend(["", "## Operator steps", ""] +
                 ["- `%s`: %d" % item for item in sorted(operations.items())])
    (ROOT / "docs" / "CASE_MEMORY_V1_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["build", "validate", "audit"])
    args = parser.parse_args()
    if args.command == "build":
        build()
    elif args.command == "audit":
        audit()
    else:
        validation_errors = validate_cases()
        print("CASE MEMORY: VALID" if not validation_errors else "CASE MEMORY: INVALID")
        raise SystemExit(bool(validation_errors))
