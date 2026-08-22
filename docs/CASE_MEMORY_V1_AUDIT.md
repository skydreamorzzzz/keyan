# Case Memory V1.1 Audit

## Information boundary

`question`, `evidence` (`qa.gold_inds`), `gold_program`, `gold_answer`, and `exe_ans` are verbatim raw FinQA fields. `table_grounding` is the exact raw row/cells consumed by each strict parsed table operator. `reasoning_trace`, numeric cells, IDs, and hashes are deterministic derivations. No target, retrieval, strategy, or LLM-generated field is present.

## Full QC

- Source coverage: 6251/6251
- QC failures: 0
- Table-grounded Cases: 198
- Trace execution: official FinQA evaluator aligned for every Case

## High-risk family audit

| Family | Case count | Step count | QC failures |
|---|---:|---:|---:|
| `literal_percentage_token` | 214 | 225 | 0 |
| `const_100` | 256 | 466 | 0 |
| `multiply_const_100` | 78 | 78 | 0 |
| `divide_percentage_conversion` | 52 | 52 | 0 |
| `multi_step_reference` | 2528 | 3144 | 0 |
| `table_sum` | 32 | 36 | 0 |
| `table_average` | 94 | 95 | 0 |
| `table_max` | 48 | 48 | 0 |
| `table_min` | 27 | 27 | 0 |
| `greater` | 124 | 124 | 0 |
| `exp` | 5 | 5 | 0 |
| `three_or_more_steps` | 521 | 1855 | 0 |

## Operator steps

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
