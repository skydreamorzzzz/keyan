"""Offline TAT-QA Strategy structure audit.

This script designs deterministic, non-LLM abstractions for TAT-QA train
samples. It does not construct a final Strategy Memory pool and does not call
any model/API.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if os.path.dirname(__file__) not in sys.path:
    sys.path.insert(0, os.path.dirname(__file__))

from tatqa_ingest import parse_split  # noqa: E402

OUT_DIR = os.path.join(ROOT, "pilot", "multibench", "output", "tatqa")
AUDIT_JSON_PATH = os.path.join(OUT_DIR, "tatqa_strategy_structure_audit.json")
AUDIT_MD_PATH = os.path.join(OUT_DIR, "TATQA_STRATEGY_STRUCTURE_AUDIT.md")

NUMBER_RE = re.compile(
    r"""
    (?<![A-Za-z])
    \$?
    (?:
        \d{1,3}(?:,\d{3})+(?:\.\d+)?
        |
        \d+(?:\.\d+)?
        |
        \.\d+
    )
    %?
    """,
    re.VERBOSE,
)
UNIT_RE = re.compile(r"\b(thousand|thousands|million|millions|billion|billions)\b", re.I)
WORD_RE = re.compile(r"[A-Za-z]+")
OP_CHARS = {"+": "add", "-": "subtract", "*": "multiply", "/": "divide"}


def dump_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def pct(count: int, total: int) -> float:
    return count / total if total else 0.0


def label(value: Any, none_label: str = "none") -> str:
    return str(value) if value not in (None, "") else none_label


def normalize_question_template(question: str) -> str:
    text = question.lower()
    text = NUMBER_RE.sub("<num>", text)
    text = re.sub(r"\b(19|20)\d{2}\b", "<year>", text)
    text = re.sub(r"\b(company|corporation|inc|ltd|plc|group)\b", "<entity>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize_derivation(derivation: str) -> list[str]:
    normalized = (
        derivation.replace("×", "*")
        .replace("÷", "/")
        .replace("[", "(")
        .replace("]", ")")
        .replace("–", "-")
        .replace("−", "-")
    )
    normalized = UNIT_RE.sub(" UNIT ", normalized)
    tokens = []
    i = 0
    operand_idx = 1
    while i < len(normalized):
        ch = normalized[i]
        if ch == "-":
            j = i + 1
            while j < len(normalized) and normalized[j].isspace():
                j += 1
            prev = previous_non_space(normalized, i)
            if j < len(normalized) and (normalized[j].isdigit() or normalized[j] in "$.") and prev in {None, "(", "+", "-", "*", "/"}:
                m = NUMBER_RE.match(normalized, j)
                if m:
                    tokens.append(f"O{operand_idx}")
                    operand_idx += 1
                    i = m.end()
                    continue
            tokens.append("-")
            i += 1
            continue
        m = NUMBER_RE.match(normalized, i)
        if m:
            tokens.append(f"O{operand_idx}")
            operand_idx += 1
            i = m.end()
            continue
        if ch in "+-*/()":
            tokens.append(ch)
        elif normalized.startswith("UNIT", i):
            tokens.append("UNIT")
            i += len("UNIT") - 1
        elif ch == "#":
            tokens.append("#")
        elif ch.isalpha():
            wm = WORD_RE.match(normalized, i)
            if wm:
                tokens.append("WORD")
                i = wm.end()
                continue
        i += 1
    return collapse_tokens(tokens)


def previous_non_space(text: str, pos: int) -> str | None:
    j = pos - 1
    while j >= 0 and text[j].isspace():
        j -= 1
    return text[j] if j >= 0 else None


def collapse_tokens(tokens: list[str]) -> list[str]:
    out = []
    for t in tokens:
        if t == "WORD" and out and out[-1] == "WORD":
            continue
        if t == "UNIT" and out and out[-1] == "UNIT":
            continue
        out.append(t)
    return out


def normalized_derivation(derivation: str) -> str:
    return " ".join(tokenize_derivation(derivation))


def operator_sequence_from_tokens(tokens: list[str]) -> list[str]:
    ops = []
    prev = None
    for t in tokens:
        if t in OP_CHARS:
            if t == "-" and prev in (None, "(", "+", "-", "*", "/"):
                prev = t
                continue
            ops.append(OP_CHARS[t])
        prev = t
    return ops


def max_parenthesis_depth(tokens: list[str]) -> int:
    depth = max_depth = 0
    for t in tokens:
        if t == "(":
            depth += 1
            max_depth = max(max_depth, depth)
        elif t == ")":
            depth = max(depth - 1, 0)
    return max_depth


def operand_count(tokens: list[str]) -> int:
    return sum(1 for t in tokens if re.fullmatch(r"O\d+", t))


def arithmetic_family_from_tokens(tokens: list[str]) -> str:
    ops = operator_sequence_from_tokens(tokens)
    op_counts = Counter(ops)
    norm = " ".join(tokens)
    if not ops:
        return "arithmetic:unparsed"
    if ops == ["subtract", "divide"] and norm.startswith("( O") and "/ O" in norm:
        return "arithmetic:percent_change"
    if ops == ["divide"] and "+" in tokens and operand_count(tokens) >= 3:
        return "arithmetic:average_or_sum_divide"
    if ops == ["divide"] and operand_count(tokens) == 2:
        return "arithmetic:ratio"
    if ops == ["subtract"] and operand_count(tokens) == 2:
        return "arithmetic:difference"
    if ops == ["add"] and operand_count(tokens) >= 2:
        return "arithmetic:sum"
    if ops == ["multiply"] and operand_count(tokens) == 2:
        return "arithmetic:product"
    if op_counts["divide"] and op_counts["subtract"]:
        return "arithmetic:change_or_composed_ratio"
    if op_counts["divide"]:
        return "arithmetic:division_composition"
    if op_counts["subtract"]:
        return "arithmetic:difference_composition"
    if op_counts["add"]:
        return "arithmetic:aggregation"
    if op_counts["multiply"]:
        return "arithmetic:multiplication_composition"
    return "arithmetic:other"


def abstract_arithmetic(record: dict[str, Any]) -> dict[str, Any]:
    derivation = record.get("derivation") or ""
    tokens = tokenize_derivation(derivation)
    ops = operator_sequence_from_tokens(tokens)
    return {
        "strategy_type": "arithmetic",
        "abstraction_reliability": "high" if derivation and ops else "low",
        "normalized_derivation": " ".join(tokens),
        "operator_sequence": ops,
        "operator_multiset": dict(Counter(ops)),
        "family": arithmetic_family_from_tokens(tokens),
        "operand_count": operand_count(tokens),
        "n_ops": len(ops),
        "max_parenthesis_depth": max_parenthesis_depth(tokens),
        "answer_from": label(record.get("answer_from")),
        "scale": label(record.get("scale")),
    }


def abstract_non_arithmetic(record: dict[str, Any]) -> dict[str, Any]:
    answer_type = record.get("answer_type")
    answer_from = label(record.get("answer_from"))
    scale = label(record.get("scale"))
    req_comparison = bool(record.get("reasoning_annotation", {}).get("req_comparison"))
    q_template = normalize_question_template(record.get("question", ""))
    if req_comparison:
        family = f"comparison:{answer_from}:scale={scale}"
        strategy_type = "comparison"
        reliability = "medium"
    elif answer_type == "span":
        family = f"span_lookup:{answer_from}:scale={scale}"
        strategy_type = "span_lookup"
        reliability = "medium"
    elif answer_type == "multi-span":
        family = f"multi_span_lookup:{answer_from}:scale={scale}"
        strategy_type = "multi_span_lookup"
        reliability = "medium"
    elif answer_type == "count":
        family = f"count:{answer_from}:scale={scale}"
        strategy_type = "count"
        reliability = "medium"
    else:
        family = f"other:{label(answer_type)}:{answer_from}:scale={scale}"
        strategy_type = "other"
        reliability = "low"
    return {
        "strategy_type": strategy_type,
        "abstraction_reliability": reliability,
        "family": family,
        "question_template": q_template,
        "operator_sequence": [],
        "operand_count": 0,
        "n_ops": 0,
        "max_parenthesis_depth": 0,
        "answer_from": answer_from,
        "scale": scale,
        "req_comparison": req_comparison,
    }


def abstract_record(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("answer_type") == "arithmetic":
        abstraction = abstract_arithmetic(record)
    else:
        abstraction = abstract_non_arithmetic(record)
    schema_key = "|".join([
        abstraction["strategy_type"],
        abstraction["family"],
        f"from={abstraction['answer_from']}",
        f"scale={abstraction['scale']}",
    ])
    return {
        "sample_id": record["sample_id"],
        "source_id": record["source_id"],
        "answer_type": label(record.get("answer_type"), "missing"),
        "answer_from": label(record.get("answer_from"), "missing"),
        "scale": label(record.get("scale")),
        "derivation": record.get("derivation") or "",
        "operator": label(record.get("operator"), "missing"),
        "ingest_operator_sequence": record.get("operator_sequence") or [],
        "schema_key": schema_key,
        **abstraction,
    }


def top_items(counter: Counter, n: int = 20) -> list[dict[str, Any]]:
    total = sum(counter.values())
    return [{"key": k, "count": v, "rate": pct(v, total)} for k, v in counter.most_common(n)]


def cumulative_coverage(counter: Counter, cutoffs: list[int]) -> dict[str, float]:
    counts = [v for _, v in counter.most_common()]
    total = sum(counts)
    return {f"top_{k}": pct(sum(counts[:k]), total) for k in cutoffs}


def summarize(records: list[dict[str, Any]], abstractions: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(records)
    answer_type = Counter(label(r.get("answer_type"), "missing") for r in records)
    answer_from = Counter(label(r.get("answer_from"), "missing") for r in records)
    scale = Counter(label(r.get("scale")) for r in records)
    op_seq = Counter(">".join(a["operator_sequence"]) if a["operator_sequence"] else "none" for a in abstractions)
    joint = Counter(
        (
            label(r.get("answer_type"), "missing"),
            a["family"],
            label(r.get("answer_from"), "missing"),
            label(r.get("scale")),
        )
        for r, a in zip(records, abstractions)
    )
    joint_type_deriv_op_from_scale = Counter(
        (
            label(r.get("answer_type"), "missing"),
            "derivation" if r.get("derivation") else "no_derivation",
            ">".join(a["operator_sequence"]) if a["operator_sequence"] else "none",
            label(r.get("answer_from"), "missing"),
            label(r.get("scale")),
        )
        for r, a in zip(records, abstractions)
    )
    schema_counter = Counter(a["schema_key"] for a in abstractions)
    family_counter = Counter(a["family"] for a in abstractions)
    reliability = Counter(a["abstraction_reliability"] for a in abstractions)
    type_family = defaultdict(Counter)
    for a in abstractions:
        type_family[a["strategy_type"]][a["family"]] += 1
    arithmetic = [a for a in abstractions if a["strategy_type"] == "arithmetic"]
    non_arithmetic = [a for a in abstractions if a["strategy_type"] != "arithmetic"]
    reliable = [a for a in abstractions if a["abstraction_reliability"] in {"high", "medium"}]
    derivation_present = sum(1 for r in records if bool(r.get("derivation")))
    derivation_by_type = {
        k: {
            "count": v,
            "derivation_present": sum(1 for r in records if label(r.get("answer_type"), "missing") == k and bool(r.get("derivation"))),
        }
        for k, v in answer_type.items()
    }
    for k in derivation_by_type:
        derivation_by_type[k]["derivation_coverage"] = pct(
            derivation_by_type[k]["derivation_present"], derivation_by_type[k]["count"]
        )
    return {
        "n_train": n,
        "answer_type": dict(answer_type),
        "answer_from": dict(answer_from),
        "scale": dict(scale),
        "derivation_present": derivation_present,
        "derivation_coverage": pct(derivation_present, n),
        "derivation_by_answer_type": derivation_by_type,
        "operator_sequence_top": top_items(op_seq, 20),
        "joint_answer_derivation_opseq_from_scale_top": [
            {
                "answer_type": k[0],
                "derivation": k[1],
                "operator_sequence": k[2],
                "answer_from": k[3],
                "scale": k[4],
                "count": v,
                "rate": pct(v, n),
            }
            for k, v in joint_type_deriv_op_from_scale.most_common(30)
        ],
        "joint_answer_family_from_scale_top": [
            {"answer_type": k[0], "family": k[1], "answer_from": k[2], "scale": k[3], "count": v, "rate": pct(v, n)}
            for k, v in joint.most_common(30)
        ],
        "abstraction_reliability": dict(reliability),
        "reliably_abstractable_count": len(reliable),
        "reliably_abstractable_rate": pct(len(reliable), n),
        "arithmetic_count": len(arithmetic),
        "non_arithmetic_count": len(non_arithmetic),
        "strategy_family_count": len(family_counter),
        "schema_family_count": len(schema_counter),
        "family_top": top_items(family_counter, 30),
        "schema_top": top_items(schema_counter, 30),
        "schema_cumulative_coverage": cumulative_coverage(schema_counter, [5, 10, 20, 50, 100]),
        "family_cumulative_coverage": cumulative_coverage(family_counter, [5, 10, 20, 50, 100]),
        "families_by_strategy_type": {
            k: {
                "family_count": len(v),
                "top_families": top_items(v, 10),
            }
            for k, v in sorted(type_family.items())
        },
        "arithmetic_examples": [
            {
                "sample_id": a["sample_id"],
                "derivation": a["derivation"],
                "normalized_derivation": a["normalized_derivation"],
                "operator_sequence": a["operator_sequence"],
                "family": a["family"],
                "scale": a["scale"],
            }
            for a in arithmetic[:25]
        ],
    }


def write_report(summary: dict[str, Any]) -> None:
    lines = [
        "# TAT-QA Strategy Structure Audit",
        "",
        "Date: 2026-08-16",
        "",
        "Scope: deterministic offline structure audit over TAT-QA train only. No LLM/API calls, no Strategy Memory construction, no four-arm experiment, no router.",
        "",
        "## Train Distribution",
        "",
        f"- Train samples: {summary['n_train']}.",
        f"- Answer type: `{summary['answer_type']}`.",
        f"- Answer source: `{summary['answer_from']}`.",
        f"- Scale: `{summary['scale']}`.",
        f"- Derivation present: {summary['derivation_present']} ({summary['derivation_coverage']:.3f}).",
        "",
        "| Answer type | Count | Derivation present | Coverage |",
        "|---|---:|---:|---:|",
    ]
    for k, v in sorted(summary["derivation_by_answer_type"].items(), key=lambda kv: -kv[1]["count"]):
        lines.append(f"| `{k}` | {v['count']} | {v['derivation_present']} | {v['derivation_coverage']:.3f} |")
    lines.extend([
        "",
        "Top joint combinations of answer type, derivation presence, operator sequence, answer source, and scale:",
        "",
        "| Answer type | Derivation | Operator sequence | Source | Scale | Count | Rate |",
        "|---|---|---|---|---|---:|---:|",
    ])
    for item in summary["joint_answer_derivation_opseq_from_scale_top"][:20]:
        lines.append(
            f"| `{item['answer_type']}` | `{item['derivation']}` | `{item['operator_sequence']}` | "
            f"`{item['answer_from']}` | `{item['scale']}` | {item['count']} | {item['rate']:.3f} |"
        )
    lines.extend([
        "",
        "## Operator Sequence Coverage",
        "",
        "| Operator sequence | Count | Rate |",
        "|---|---:|---:|",
    ])
    for item in summary["operator_sequence_top"][:15]:
        lines.append(f"| `{item['key']}` | {item['count']} | {item['rate']:.3f} |")
    lines.extend([
        "",
        "## Deterministic Arithmetic Normalization",
        "",
        "Arithmetic derivations are treated as TAT-QA formula strings, not FinQA programs. The normalization:",
        "",
        "- replaces concrete numeric literals, years, percentages, and currency-marked numbers with ordered operand placeholders `O1`, `O2`, ...;",
        "- removes specific units into `UNIT` markers when they appear inside the formula;",
        "- preserves only arithmetic operators, parentheses, operand count, operation order, and coarse composed family;",
        "- does not attempt to recover table cell references or convert formulas into the FinQA DSL.",
        "",
        "Examples:",
        "",
        "| Raw derivation | Normalized | Operators | Family | Scale |",
        "|---|---|---|---|---|",
    ])
    for ex in summary["arithmetic_examples"][:12]:
        raw = ex["derivation"].replace("|", "\\|")[:80]
        norm = ex["normalized_derivation"].replace("|", "\\|")[:100]
        lines.append(
            f"| `{raw}` | `{norm}` | `{'>'.join(ex['operator_sequence'])}` | `{ex['family']}` | `{ex['scale']}` |"
        )
    lines.extend([
        "",
        "## Span / Multi-Span / Count / Comparison",
        "",
        "- `span_lookup`: should form Strategy as evidence-location and value-normalization guidance, not arithmetic procedure.",
        "- `multi_span_lookup`: should form Strategy for collecting multiple values/labels from table/text and preserving answer granularity.",
        "- `count`: should form Strategy only as deterministic counting over listed conditions/items; support is smaller, so keep separate from arithmetic.",
        "- `comparison`: should form Strategy as table/text comparison with direction and yes/no or span-like output handling. It is not equivalent to subtraction unless the question asks for a numeric difference.",
        "",
        "Recommended non-arithmetic abstraction fields: `strategy_type`, `answer_from`, `scale`, `question_template`, `req_comparison`, and source evidence mode. Do not use answer strings as strategy text.",
        "",
        "## Proposed Unified TAT-QA Strategy Schema",
        "",
        "```json",
        "{",
        '  "strategy_id": "tatqa_strategy:<family_hash>",',
        '  "dataset_id": "tatqa",',
        '  "strategy_type": "arithmetic | span_lookup | multi_span_lookup | count | comparison",',
        '  "family": "coarse deterministic family",',
        '  "answer_from": "table | text | table-text",',
        '  "scale": "none | percent | thousand | million | billion",',
        '  "normalized_derivation": "O1 / O2, etc. for arithmetic only",',
        '  "operator_sequence": ["subtract", "divide"],',
        '  "operand_count": 2,',
        '  "max_parenthesis_depth": 1,',
        '  "question_template": "label-free question pattern for lookup strategies",',
        '  "source_support_count": 123,',
        '  "source_sample_ids": ["tatqa:train:..."],',
        '  "retrieval_text": "label-free strategy description generated from schema fields only"',
        "}",
        "```",
        "",
        "## Strategy Family Statistics",
        "",
        f"- Reliably abstractable train samples: {summary['reliably_abstractable_count']} ({summary['reliably_abstractable_rate']:.3f}).",
        f"- Coarse strategy families: {summary['strategy_family_count']}.",
        f"- Schema families after including answer_from/scale: {summary['schema_family_count']}.",
        f"- Coarse family cumulative coverage: `{summary['family_cumulative_coverage']}`.",
        f"- Schema cumulative coverage: `{summary['schema_cumulative_coverage']}`.",
        "",
        "| Top family | Count | Rate |",
        "|---|---:|---:|",
    ])
    for item in summary["family_top"][:20]:
        lines.append(f"| `{item['key']}` | {item['count']} | {item['rate']:.3f} |")
    lines.extend([
        "",
        "Top schema families:",
        "",
        "| Schema family | Count | Rate |",
        "|---|---:|---:|",
    ])
    for item in summary["schema_top"][:20]:
        lines.append(f"| `{item['key']}` | {item['count']} | {item['rate']:.3f} |")
    lines.extend([
        "",
        "## Inclusion Recommendation",
        "",
        "- Include arithmetic samples with non-empty derivation and at least one parsed operator as procedural strategies.",
        "- Include span and multi-span as lookup/evidence selection strategies, not as arithmetic strategies.",
        "- Include count and comparison as separate small strategy types; do not merge comparison into numeric difference unless the annotation is arithmetic.",
        "- Exclude or mark low-confidence only samples with missing answer_type or arithmetic derivations that parse to no operator.",
        "",
        "## LLM Abstraction Next Step",
        "",
        "A small LLM pass is worth doing next, but only after freezing this deterministic schema. The highest-value use is semantic wording of strategy descriptions from schema fields and representative train examples, not inventing new families. Arithmetic formula families are already recoverable deterministically; span/comparison strategies need semantic abstraction for evidence-location cues.",
        "",
        "Decision: `PROCEED TO SMALL-LLM TAT-QA STRATEGY ABSTRACTION PILOT`.",
    ])
    with open(AUDIT_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run() -> dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True)
    train = parse_split("train")
    abstractions = [abstract_record(r) for r in train]
    summary = summarize(train, abstractions)
    artifact = {
        "summary": summary,
        "schema_version": "tatqa_strategy_structure_v1",
        "notes": [
            "Offline deterministic audit only.",
            "Gold labels are used only because this is train-side strategy design, not inference-time routing.",
            "No LLM/API calls.",
        ],
    }
    dump_json(AUDIT_JSON_PATH, artifact)
    write_report(summary)
    print(json.dumps({
        "train": summary["n_train"],
        "reliably_abstractable_rate": summary["reliably_abstractable_rate"],
        "strategy_family_count": summary["strategy_family_count"],
        "schema_family_count": summary["schema_family_count"],
        "report": os.path.relpath(AUDIT_MD_PATH, ROOT),
        "json": os.path.relpath(AUDIT_JSON_PATH, ROOT),
    }, indent=2))
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
