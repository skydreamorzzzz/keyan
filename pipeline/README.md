# Canonical FinQA Data Pipeline v1.1

`python -m pipeline.build` first checks the committed immutable upstream lock, validates every gold program, then builds into a temporary directory and atomically publishes only a fully validated tree. It creates an immutable train source pool, separate dev (development only) and test (final evaluation only) target pools, an ID-keyed question embedding ledger, and separate frozen top-3 retrieval manifests under `artifacts/finqa_v1/`.

`python -m pipeline.validate` is the release gate. It verifies every manifest's records byte hash and parent byte hash, re-executes every FinQA gold program with both official and custom executors, and recomputes every dev and test retrieval row. It prints exactly `CANONICAL DATASET: VALID` or `CANONICAL DATASET: INVALID` (use `--details` for diagnostics).

`retrieval_question_v1` is retrieval text, not a Case Memory representation. Future memory representations must be separate versioned, QC-gated artifacts and may not change `source_pool.jsonl`.
