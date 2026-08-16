# TAT-QA Strategy Retrieval Audit

Date: 2026-08-16

Scope: retrieval-only audit for frozen `tatqa_strategy_memory_v0.json`. No LLM/API calls, no strategy edits, no family changes, no four-arm execution, no router.

## Setup

- Strategy memory: 30 frozen strategies.
- Retriever: same dense embedding model as FinQA pilot, `BAAI/bge-small-en-v1.5` on `cpu`.
- Top-k: 3.
- Fixed dev sample: 120 examples, seed `20260816`.
- Target query text uses only inference-time visible question, paragraphs, and table via `tatqa_case_memory.make_retrieval_text(..., memory_side=False)`.
- Gold schema/type/source/scale are used only after retrieval for diagnostics.

## Coverage

- Gold schema present in frozen memory for 111 / 120 dev samples (0.925).
- Samples outside this coverage cannot have exact schema hit by construction; type/family/source/scale diagnostics are still reported.

## Retrieval-Text Ablation

| Variant | Exact schema top1 | Exact schema top3 | Type top1 | Type top3 | Family top3 | Source top3 | Scale top3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Semantic-rich, all samples | 0.075 | 0.192 | 0.317 | 0.675 | 0.208 | 0.783 | 0.658 |
| Schema-only, all samples | 0.058 | 0.183 | 0.425 | 0.433 | 0.258 | 0.633 | 0.608 |
| Semantic-rich, eligible only | 0.081 | 0.207 | 0.342 | 0.721 | 0.225 | 0.784 | 0.676 |
| Schema-only, eligible only | 0.063 | 0.198 | 0.387 | 0.396 | 0.270 | 0.640 | 0.595 |

Semantic-rich minus schema-only exact schema top3 on eligible samples: +0.009.
Semantic-rich minus schema-only strategy-type top3 on all samples: +0.242.

## By Strategy Type

| Type | N | Eligible | Semantic schema top3 | Schema-only schema top3 | Semantic type top3 | Schema-only type top3 |
|---|---:|---:|---:|---:|---:|---:|
| `arithmetic` | 52 | 44 | 0.135 | 0.423 | 0.385 | 1.000 |
| `comparison` | 4 | 4 | 0.000 | 0.000 | 0.000 | 0.000 |
| `count` | 1 | 1 | 0.000 | 0.000 | 0.000 | 0.000 |
| `multi_span_lookup` | 12 | 12 | 0.250 | 0.000 | 0.917 | 0.000 |
| `span_lookup` | 51 | 50 | 0.255 | 0.000 | 0.980 | 0.000 |

## Typical Correct Retrievals

- `tatqa:dev:a2d14f8f-9600-421d-8936-68823992ccf0`: gold `span_lookup|span_lookup:text:scale=none|from=text|scale=none`; top3 `['multi_span_lookup|multi_span_lookup:text:scale=none|from=text|scale=none', 'span_lookup|span_lookup:text:scale=none|from=text|scale=none', 'span_lookup|span_lookup:table:scale=million|from=table|scale=million']`; question: When did the FASB issued new authoritative guidance for revenue from contracts with customers?
- `tatqa:dev:7836af77-b8af-4409-a56b-e11f1cf414e6`: gold `span_lookup|span_lookup:table:scale=none|from=table|scale=none`; top3 `['span_lookup|span_lookup:table:scale=none|from=table|scale=none', 'span_lookup|span_lookup:table-text:scale=none|from=table-text|scale=none', 'multi_span_lookup|multi_span_lookup:text:scale=none|from=text|scale=none']`; question: What is the number of non-vested shares vested in 2019?
- `tatqa:dev:816f3f4c-28fd-4382-b7be-f65902ec3fb7`: gold `span_lookup|span_lookup:text:scale=none|from=text|scale=none`; top3 `['multi_span_lookup|multi_span_lookup:text:scale=none|from=text|scale=none', 'span_lookup|span_lookup:table-text:scale=none|from=table-text|scale=none', 'span_lookup|span_lookup:text:scale=none|from=text|scale=none']`; question: What was the reason for the increase in the Orders?
- `tatqa:dev:785fc2be-fc6d-456e-af36-8c5f1c7fd1c9`: gold `span_lookup|span_lookup:text:scale=none|from=text|scale=none`; top3 `['multi_span_lookup|multi_span_lookup:text:scale=none|from=text|scale=none', 'span_lookup|span_lookup:text:scale=none|from=text|scale=none', 'span_lookup|span_lookup:table:scale=none|from=table|scale=none']`; question: What does the Fiscal 2017 Restructuring Plan charges relate to?
- `tatqa:dev:234336c9-fc8a-40e8-bdb2-c16c64bc05d7`: gold `span_lookup|span_lookup:table-text:scale=none|from=table-text|scale=none`; top3 `['span_lookup|span_lookup:table-text:scale=none|from=table-text|scale=none', 'span_lookup|span_lookup:table:scale=none|from=table|scale=none', 'span_lookup|span_lookup:table:scale=million|from=table|scale=million']`; question: What is the Free Cash Flow in 2018?

## Typical Errors

- `tatqa:dev:2e7201fb-3eb2-44c0-ba33-4a161e8dd664`: gold `span_lookup|span_lookup:table-text:scale=million|from=table-text|scale=million`; top1 `multi_span_lookup|multi_span_lookup:text:scale=none|from=text|scale=none`; top3 `['multi_span_lookup|multi_span_lookup:text:scale=none|from=text|scale=none', 'span_lookup|span_lookup:table-text:scale=none|from=table-text|scale=none', 'span_lookup|span_lookup:table:scale=none|from=table|scale=none']`; question: What was the Pre-tax losses on sale of receivables in 2018?
- `tatqa:dev:06e79509-49d3-47c4-94a9-1ca382cb11c3`: gold `span_lookup|span_lookup:text:scale=none|from=text|scale=none`; top1 `span_lookup|span_lookup:table:scale=none|from=table|scale=none`; top3 `['span_lookup|span_lookup:table:scale=none|from=table|scale=none', 'span_lookup|span_lookup:table:scale=million|from=table|scale=million', 'multi_span_lookup|multi_span_lookup:text:scale=none|from=text|scale=none']`; question: What is the Company's valuation allowance against its U.S deferred tax assets as of December 31, 2019?
- `tatqa:dev:6b289db7-2ee8-48ec-a257-e7e8f9640f1c`: gold `span_lookup|span_lookup:table:scale=million|from=table|scale=million`; top1 `multi_span_lookup|multi_span_lookup:text:scale=none|from=text|scale=none`; top3 `['multi_span_lookup|multi_span_lookup:text:scale=none|from=text|scale=none', 'span_lookup|span_lookup:table:scale=none|from=table|scale=none', 'multi_span_lookup|multi_span_lookup:table-text:scale=none|from=table-text|scale=none']`; question: What is the total assets for year 2019?
- `tatqa:dev:81fc6048-7510-4c55-aa3c-4c9f1f5b8bcb`: gold `arithmetic|arithmetic:percent_change|from=table-text|scale=percent`; top1 `span_lookup|span_lookup:table-text:scale=none|from=table-text|scale=none`; top3 `['span_lookup|span_lookup:table-text:scale=none|from=table-text|scale=none', 'multi_span_lookup|multi_span_lookup:text:scale=none|from=text|scale=none', 'span_lookup|span_lookup:table:scale=none|from=table|scale=none']`; question: What was the change in the servicing fee between 2018 and 2019?
- `tatqa:dev:f1eedc55-cc96-4574-b82b-e6f17cf176af`: gold `span_lookup|span_lookup:table-text:scale=none|from=table-text|scale=none`; top1 `multi_span_lookup|multi_span_lookup:text:scale=none|from=text|scale=none`; top3 `['multi_span_lookup|multi_span_lookup:text:scale=none|from=text|scale=none', 'span_lookup|span_lookup:text:scale=none|from=text|scale=none', 'span_lookup|span_lookup:table:scale=none|from=table|scale=none']`; question: What was the increase in interest income in 2019?

## Interpretation

Semantic abstraction improves retrieval alignment over schema-only metadata in this fixed audit.

Main failure modes:

- Frozen v0 covers only top-30 train schema families, so exact schema retrieval is impossible for out-of-memory dev schemas.
- Dense retrieval sometimes overweights semantic surface cues such as lookup/comparison wording and misses source/scale-specific schema variants.
- Arithmetic strategy families are schema-heavy; natural language question/context similarity can retrieve a nearby arithmetic family but wrong source or scale.
- The current target query includes full context, which can add evidence text that pulls toward lookup strategies even when the gold schema is arithmetic.

## Decision

Decision: `NEEDS STRATEGY RETRIEVAL REVISION BEFORE FOUR-ARM DRY-RUN`.
