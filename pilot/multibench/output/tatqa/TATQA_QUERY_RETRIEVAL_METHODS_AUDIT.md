# TAT-QA Query Retrieval Methods Audit

Date: 2026-08-16

Scope: Strategy retrieval query-method audit only. Frozen 30-item Strategy Memory, same 120-sample dev audit set, same embedding model, same top-3. No four-arm execution, no router, no strategy rewriting or family changes.

## Setup

- Strategy memory: `data/tatqa/processed/tatqa_strategy_memory_v0.json` (30 frozen strategies).
- Fixed dev sample: 120 examples, seed `20260816`.
- Gold schema present in frozen memory: 111 / 120 (0.925).
- Retriever: `BAAI/bge-small-en-v1.5` on `cpu`, top-3.
- Query-generation records required: 120 (one DeepSeek call per sample when cache is cold; each call returns both rewrite and HyDE).
- Latest command API calls: 0; cache hits: 120; cache records after run: 120.

The rewrite/HyDE prompt used only the raw question text. It did not include gold answer, answer_type, scale, operator, derivation, or schema labels.

## Overall Results

| Method | Schema top1 | Schema top3 | Type top3 | Family top3 | Source top3 | Scale top3 |
|---|---:|---:|---:|---:|---:|---:|
| `question_only` all | 0.133 | 0.275 | 0.717 | 0.292 | 0.758 | 0.725 |
| `query_rewrite` all | 0.117 | 0.300 | 0.667 | 0.308 | 0.792 | 0.767 |
| `hyde` all | 0.133 | 0.358 | 0.750 | 0.400 | 0.833 | 0.783 |

Eligible-only exact schema results:

| Method | Schema top1 | Schema top3 | Type top3 | Family top3 |
|---|---:|---:|---:|---:|
| `question_only` | 0.144 | 0.297 | 0.757 | 0.315 |
| `query_rewrite` | 0.126 | 0.324 | 0.712 | 0.333 |
| `hyde` | 0.144 | 0.387 | 0.811 | 0.432 |

## By Strategy Type

| Type | N | Method | Schema top3 | Type top3 | Family top3 |
|---|---:|---|---:|---:|---:|
| `arithmetic` | 52 | `question_only` | 0.288 | 0.635 | 0.327 |
| `arithmetic` | 52 | `query_rewrite` | 0.327 | 0.519 | 0.346 |
| `arithmetic` | 52 | `hyde` | 0.365 | 0.519 | 0.462 |
| `comparison` | 4 | `question_only` | 0.750 | 0.750 | 0.750 |
| `comparison` | 4 | `query_rewrite` | 1.000 | 1.000 | 1.000 |
| `comparison` | 4 | `hyde` | 1.000 | 1.000 | 1.000 |
| `count` | 1 | `question_only` | 1.000 | 1.000 | 1.000 |
| `count` | 1 | `query_rewrite` | 1.000 | 1.000 | 1.000 |
| `count` | 1 | `hyde` | 1.000 | 1.000 | 1.000 |
| `multi_span_lookup` | 12 | `question_only` | 0.250 | 0.917 | 0.250 |
| `multi_span_lookup` | 12 | `query_rewrite` | 0.167 | 0.750 | 0.167 |
| `multi_span_lookup` | 12 | `hyde` | 0.417 | 0.833 | 0.417 |
| `span_lookup` | 51 | `question_only` | 0.216 | 0.745 | 0.216 |
| `span_lookup` | 51 | `query_rewrite` | 0.235 | 0.765 | 0.235 |
| `span_lookup` | 51 | `hyde` | 0.275 | 0.941 | 0.275 |

## Typical Successes

- `tatqa:dev:2e7201fb-3eb2-44c0-ba33-4a161e8dd664` gold `span_lookup|span_lookup:table-text:scale=million|from=table-text|scale=million`; hyde top3 `['span_lookup|span_lookup:table-text:scale=million|from=table-text|scale=million', 'comparison|comparison:table:scale=none|from=table|scale=none', 'span_lookup|span_lookup:table-text:scale=thousand|from=table-text|scale=thousand']`; question: What was the Pre-tax losses on sale of receivables in 2018?
- `tatqa:dev:6b289db7-2ee8-48ec-a257-e7e8f9640f1c` gold `span_lookup|span_lookup:table:scale=million|from=table|scale=million`; hyde top3 `['span_lookup|span_lookup:table-text:scale=million|from=table-text|scale=million', 'span_lookup|span_lookup:table:scale=million|from=table|scale=million', 'span_lookup|span_lookup:table:scale=thousand|from=table|scale=thousand']`; question: What is the total assets for year 2019?
- `tatqa:dev:7836af77-b8af-4409-a56b-e11f1cf414e6` gold `span_lookup|span_lookup:table:scale=none|from=table|scale=none`; hyde top3 `['span_lookup|span_lookup:table:scale=none|from=table|scale=none', 'span_lookup|span_lookup:table:scale=million|from=table|scale=million', 'count|count:table-text:scale=none|from=table-text|scale=none']`; question: What is the number of non-vested shares vested in 2019?
- `tatqa:dev:62f8f0d9-7670-40aa-9a54-86df84c7df25` gold `span_lookup|span_lookup:text:scale=none|from=text|scale=none`; hyde top3 `['span_lookup|span_lookup:table-text:scale=none|from=table-text|scale=none', 'span_lookup|span_lookup:table-text:scale=thousand|from=table-text|scale=thousand', 'span_lookup|span_lookup:text:scale=none|from=text|scale=none']`; question: What is another name for the defined benefit plan?
- `tatqa:dev:c07943fa-5f7e-467e-aaea-2f064d71a874` gold `comparison|comparison:table:scale=none|from=table|scale=none`; hyde top3 `['comparison|comparison:table:scale=none|from=table|scale=none', 'comparison|comparison:table-text:scale=none|from=table-text|scale=none', 'count|count:table-text:scale=none|from=table-text|scale=none']`; question: In which year was the amount for Communications Solutions the largest?

## Cases Improved Over Question-Only

- `tatqa:dev:2e7201fb-3eb2-44c0-ba33-4a161e8dd664` gold `span_lookup|span_lookup:table-text:scale=million|from=table-text|scale=million`; question-only `['span_lookup|span_lookup:table-text:scale=thousand|from=table-text|scale=thousand', 'multi_span_lookup|multi_span_lookup:text:scale=none|from=text|scale=none', 'multi_span_lookup|multi_span_lookup:table-text:scale=thousand|from=table-text|scale=thousand']` -> hyde `['span_lookup|span_lookup:table-text:scale=million|from=table-text|scale=million', 'comparison|comparison:table:scale=none|from=table|scale=none', 'span_lookup|span_lookup:table-text:scale=thousand|from=table-text|scale=thousand']`; rewrite: extract value of a financial metric for a specific year from a table
- `tatqa:dev:62f8f0d9-7670-40aa-9a54-86df84c7df25` gold `span_lookup|span_lookup:text:scale=none|from=text|scale=none`; question-only `['multi_span_lookup|multi_span_lookup:table-text:scale=none|from=table-text|scale=none', 'multi_span_lookup|multi_span_lookup:text:scale=none|from=text|scale=none', 'span_lookup|span_lookup:table:scale=none|from=table|scale=none']` -> hyde `['span_lookup|span_lookup:table-text:scale=none|from=table-text|scale=none', 'span_lookup|span_lookup:table-text:scale=thousand|from=table-text|scale=thousand', 'span_lookup|span_lookup:text:scale=none|from=text|scale=none']`; rewrite: synonym or alternative name for a defined benefit plan
- `tatqa:dev:c07943fa-5f7e-467e-aaea-2f064d71a874` gold `comparison|comparison:table:scale=none|from=table|scale=none`; question-only `['multi_span_lookup|multi_span_lookup:text:scale=none|from=text|scale=none', 'span_lookup|span_lookup:table-text:scale=million|from=table-text|scale=million', 'span_lookup|span_lookup:table:scale=million|from=table|scale=million']` -> hyde `['comparison|comparison:table:scale=none|from=table|scale=none', 'comparison|comparison:table-text:scale=none|from=table-text|scale=none', 'count|count:table-text:scale=none|from=table-text|scale=none']`; rewrite: find year when a given category has maximum value in a table
- `tatqa:dev:816f3f4c-28fd-4382-b7be-f65902ec3fb7` gold `span_lookup|span_lookup:text:scale=none|from=text|scale=none`; question-only `['arithmetic|arithmetic:percent_change|from=table|scale=percent', 'arithmetic|arithmetic:percent_change|from=table-text|scale=percent', 'arithmetic|arithmetic:difference|from=table|scale=million']` -> hyde `['span_lookup|span_lookup:text:scale=none|from=text|scale=none', 'comparison|comparison:table-text:scale=none|from=table-text|scale=none', 'comparison|comparison:table:scale=none|from=table|scale=none']`; rewrite: reason for increase in metric, compare periods, find explanatory factor
- `tatqa:dev:c3d058ee-d553-4c2a-9ed8-0b4c1d4eee8b` gold `multi_span_lookup|multi_span_lookup:table-text:scale=none|from=table-text|scale=none`; question-only `['multi_span_lookup|multi_span_lookup:table:scale=none|from=table|scale=none', 'comparison|comparison:table:scale=none|from=table|scale=none', 'count|count:table-text:scale=none|from=table-text|scale=none']` -> hyde `['multi_span_lookup|multi_span_lookup:table:scale=none|from=table|scale=none', 'multi_span_lookup|multi_span_lookup:table-text:scale=none|from=table-text|scale=none', 'comparison|comparison:table:scale=none|from=table|scale=none']`; rewrite: How to determine the years covered in a table from its headers?

## Typical Failures

- `tatqa:dev:06e79509-49d3-47c4-94a9-1ca382cb11c3` gold `span_lookup|span_lookup:text:scale=none|from=text|scale=none`; hyde top3 `['span_lookup|span_lookup:table-text:scale=million|from=table-text|scale=million', 'span_lookup|span_lookup:table-text:scale=thousand|from=table-text|scale=thousand', 'span_lookup|span_lookup:table:scale=million|from=table|scale=million']`; HyDE: To find a specific financial figure at a given date, locate the relevant financial statement or note section, identify the line item matching the described account (e.g., valuation
- `tatqa:dev:81fc6048-7510-4c55-aa3c-4c9f1f5b8bcb` gold `arithmetic|arithmetic:percent_change|from=table-text|scale=percent`; hyde top3 `['comparison|comparison:table-text:scale=none|from=table-text|scale=none', 'comparison|comparison:table:scale=none|from=table|scale=none', 'span_lookup|span_lookup:table-text:scale=million|from=table-text|scale=million']`; HyDE: To find the change in a financial metric between two consecutive years, identify the values for each year from the table, then subtract the earlier year's value from the later year
- `tatqa:dev:f1eedc55-cc96-4574-b82b-e6f17cf176af` gold `span_lookup|span_lookup:table-text:scale=none|from=table-text|scale=none`; hyde top3 `['comparison|comparison:table-text:scale=none|from=table-text|scale=none', 'comparison|comparison:table:scale=none|from=table|scale=none', 'span_lookup|span_lookup:table-text:scale=million|from=table-text|scale=million']`; HyDE: To find the increase in a financial metric between two periods, identify the metric and the two periods from the question. Locate the values for the metric in the table for both pe
- `tatqa:dev:0b835494-2c10-4f6b-b54a-60aa73ebdabe` gold `arithmetic|arithmetic:difference|from=table|scale=percent`; hyde top3 `['comparison|comparison:table-text:scale=none|from=table-text|scale=none', 'comparison|comparison:table:scale=none|from=table|scale=none', 'span_lookup|span_lookup:table-text:scale=million|from=table-text|scale=million']`; HyDE: To find the change in a financial metric between two fiscal years, identify the metric values for each year from the table, then subtract the earlier year's value from the later ye
- `tatqa:dev:bde0702e-2847-485b-be4a-fb037790bd59` gold `span_lookup|span_lookup:text:scale=none|from=text|scale=none`; hyde top3 `['multi_span_lookup|multi_span_lookup:text:scale=none|from=text|scale=none', 'multi_span_lookup|multi_span_lookup:table-text:scale=none|from=table-text|scale=none', 'span_lookup|span_lookup:table:scale=none|from=table|scale=none']`; HyDE: Identify the geographic locations mentioned in the document where a specific type of retirement plan is offered, using the text to list the countries.

## Interpretation

Exact schema top3 on eligible samples: question-only 0.297, rewrite 0.324, HyDE 0.387.
Recommended method by exact schema top3 with type-top3 tie-break: `hyde`.

Main failure modes:

- Query-only methods still struggle to distinguish source/scale variants within the same broad family.
- Rewriting can abstract away useful lexical cues needed to separate arithmetic from lookup questions.
- HyDE often improves broad strategy type intent, but can hallucinate a generic strategy that misses exact schema source/scale.
- Frozen v0 only covers top schema families, so some dev gold schemas remain impossible exact hits.

## Decision

Decision: `FREEZE HYDE STRATEGY RETRIEVAL FOR TAT-QA FOUR-ARM SMALL DRY-RUN`.
