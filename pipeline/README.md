# Canonical FinQA Data Pipeline v1

`python -m pipeline.build --until retrieval` creates immutable source (train) and target (dev/test) pools from raw FinQA, an ID-keyed question embedding ledger, and a frozen top-3 retrieval manifest under `artifacts/finqa_v1/`.

`python -m pipeline.validate` is the release gate. It checks locks, hashes, identities, strict gold execution against the bundled FinQA official evaluator, independent custom-executor differential results, representations, embeddings, and retrieval recomputation. It prints exactly `CANONICAL DATASET: VALID` or `CANONICAL DATASET: INVALID` (use `--details` for diagnostics).

Representation artifacts are deliberately independent from the source universe: `case_v1` is deterministic and valid; Strategy and Grounded Sketch must be added as separate versioned, QC-gated artifacts without changing `source_pool.jsonl`.
