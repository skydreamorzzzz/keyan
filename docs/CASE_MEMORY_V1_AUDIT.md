# Case Memory V1 Audit

All fields are either verbatim FinQA raw (`question`, `gold_inds`, `program`, `answer`, `exe_ans`) or deterministic (`reasoning_trace`, hashes, IDs). No LLM-generated, target, retrieval, or strategy fields exist.

## QC

- Source coverage: 6251/6251
- QC failures: 0
- Trace execution: official FinQA evaluator aligned for all cases

## Operator audit

- `add`: 1512
- `divide`: 4445
- `exp`: 5
- `greater`: 124
- `multiply`: 567
- `subtract`: 2739
- `table_average`: 95
- `table_max`: 48
- `table_min`: 27
- `table_sum`: 36

## Step-count audit

- `1` steps: 3717
- `2` steps: 2013
- `3` steps: 331
- `4` steps: 94
- `5` steps: 90
- `6` steps: 6
