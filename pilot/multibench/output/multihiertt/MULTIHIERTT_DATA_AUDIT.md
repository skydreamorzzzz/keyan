# MultiHiertt Data Audit

Date: 2026-08-17

Scope: ingestion and data audit only. No LLM/API calls, no memory construction, no retrieval, no four-arm experiment, no router.

## Source

Primary source is the official MultiHiertt GitHub repository (`psunlpgroup/MultiHiertt`) and ACL 2022 paper. The raw files used here are the documented Hugging Face parquet repackaging `bevaya/MultiHiertt`, which contains train/validation annotation data without checkpoints.
See `data/multihiertt/SOURCE.md` for URLs, checksums, and license notes.

## Split Summary

| Split | Rows | Expected | Program | Span | Program parse OK | Any evidence | Missing/malformed fields |
|---|---:|---:|---:|---:|---:|---:|---|
| `train` | 7830 | 7830 | 6306 | 1524 | 1.000 | 1.000 | `{}` |
| `validation` | 1044 | 1044 | 842 | 202 | 1.000 | 1.000 | `{}` |

## Program / Operator Distribution

### train
- n_steps distribution: `{'min': 1.0, 'mean': 2.160799238820171, 'p50': 2.0, 'p90': 4.0, 'p95': 4.0, 'max': 24.0}`
- top operators: `{'add': 6515, 'divide': 3815, 'subtract': 2604, 'multiply': 681, 'exp': 11}`

### validation
- n_steps distribution: `{'min': 1.0, 'mean': 2.156769596199525, 'p50': 2.0, 'p90': 4.0, 'p95': 4.0, 'max': 16.0}`
- top operators: `{'add': 873, 'divide': 496, 'subtract': 365, 'multiply': 79, 'exp': 3}`

## Evidence Coverage

| Split | Text evidence non-empty | Table evidence non-empty | Any evidence non-empty | Text refs valid | Table refs valid |
|---|---:|---:|---:|---:|---:|
| `train` | 0.629 | 0.909 | 1.000 | 4922 | 7117 |
| `validation` | 0.676 | 0.890 | 1.000 | 706 | 929 |

## Context Length Distributions

### train
- `table_count`: `{'min': 3.0, 'mean': 4.03154533844189, 'p50': 4.0, 'p90': 6.0, 'p95': 6.0, 'max': 7.0}`
- `paragraph_count`: `{'min': 21.0, 'mean': 74.59272030651341, 'p50': 72.0, 'p90': 106.0, 'p95': 117.0, 'max': 173.0}`
- `table_description_cell_count`: `{'min': 6.0, 'mean': 129.83805874840357, 'p50': 119.0, 'p90': 209.0, 'p95': 241.0, 'max': 544.0}`
- `context_char_len`: `{'min': 6440.0, 'mean': 16235.34380587484, 'p50': 15664.0, 'p90': 21876.2, 'p95': 24794.1, 'max': 39809.0}`

### validation
- `table_count`: `{'min': 2.0, 'mean': 3.8793103448275863, 'p50': 4.0, 'p90': 5.0, 'p95': 6.0, 'max': 7.0}`
- `paragraph_count`: `{'min': 29.0, 'mean': 73.5316091954023, 'p50': 70.0, 'p90': 103.0, 'p95': 113.85, 'max': 165.0}`
- `table_description_cell_count`: `{'min': 21.0, 'mean': 135.84291187739464, 'p50': 120.0, 'p90': 223.7, 'p95': 251.85, 'max': 454.0}`
- `context_char_len`: `{'min': 8147.0, 'mean': 16237.578544061304, 'p50': 15371.0, 'p90': 21707.3, 'p95': 24353.0, 'max': 33945.0}`

## Unified IR Mapping

- `question` / `answer`: copied from parquet columns.
- `paragraphs`: list of document sentences, preserving `## Table N ##` placeholders.
- `tables`: list of raw hierarchical HTML tables, one object per table.
- `table_description`: JSON-decoded cell description mapping; not forced into a flat table matrix.
- `reasoning.program`: original MultiHiertt flat DSL string, retained as-is.
- `reasoning.operator_sequence`: deterministic parse of operator names for audit only.
- `reasoning.evidence.text` / `reasoning.evidence.table`: gold evidence ids plus resolved text/cell descriptions where available.

## Sample20

Deterministic sanity sample saved to `data/multihiertt/processed/multihiertt_unified_sample20.json` with seed `20260817`.

## Decision

Decision: `READY FOR EVALUATOR`.
