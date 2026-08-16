# TAT-QA Case Retrieval Audit

Date: 2026-08-16

Scope: TAT-QA train-only Case Memory plus retrieval-only dev audit. No LLM calls, no Strategy Memory, no four-arm experiment.

## Memory Construction

- Source split: TAT-QA train only.
- Cases: 13215.
- Saved memory: `data/tatqa/processed/tatqa_case_memory_train.json`.
- Each case stores question, table, relevant paragraphs, answer, answer type/source, scale, derivation, coarse operator, operator sequence, reasoning annotation, and `source_id`.
- Historical solved-case labels are stored for future prompting/audit, but they are not used in target query retrieval text.

## Retrieval Text Safety

- Target query retrieval text uses only inference-visible fields: question, visible paragraphs, and table.
- Case retrieval text excludes answer, answer type/source, scale, derivation, operator, and reasoning annotation.
- Post-hoc compatibility metrics below use gold labels only after retrieval, for audit diagnostics.

## Retrieval Setup

- Retriever: same dense embedding model as FinQA pilot, `BAAI/bge-small-en-v1.5` on `cpu`.
- Top-k: 4.
- TAT-QA-specific tuning: none.
- Added exclusion: retrieved cases with identical `source_id` are skipped.
- Source leak count after exclusion: 0.

## Fixed Dev Audit

- Dev sample size: 50 fixed by seed `20260816`.
- Average top-1 cosine score: 0.9254.

| Diagnostic label | Top-1 match | Any top-4 match |
|---|---:|---:|
| `answer_type` | 0.740 | 0.980 |
| `answer_from` | 0.500 | 0.760 |
| `operator` | 0.640 | 0.900 |
| `scale` | 0.540 | 0.920 |

Target label distribution in this audit sample:

- answer_type: `{'span': 26, 'arithmetic': 18, 'count': 1, 'multi-span': 5}`
- operator: `{'span': 25, 'divide': 11, 'subtract': 5, 'comparison': 1, 'add': 1, 'count': 1, 'multi_span': 5, 'multiply': 1}`
- scale: `{'million': 7, 'none': 28, 'percent': 8, 'thousand': 7}`

## Retrieval Examples

### tatqa:dev:2e7201fb-3eb2-44c0-ba33-4a161e8dd664

Question: What was the Pre-tax losses on sale of receivables in 2018?

Target audit labels: answer_type=`span`, answer_from=`table-text`, operator=`span`, scale=`million`.

| Rank | Score | Case question | Answer type | Operator | Scale |
|---:|---:|---|---|---|---|
| 1 | 0.9730 | What were the Pre-tax losses on sale of receivables in 2018? | `span` | `span` | `million` |
| 2 | 0.9448 | What was the percentage change in Pre-tax losses on sale of receivables between 2017 and 2018? | `arithmetic` | `divide` | `percent` |
| 3 | 0.9407 | What was the change in Trade accounts receivable sold between 2018 and 2019? | `arithmetic` | `subtract` | `million` |
| 4 | 0.9175 | Which years does the table provide data for trade accounts receivable sold? | `multi-span` | `multi_span` | `` |

### tatqa:dev:06e79509-49d3-47c4-94a9-1ca382cb11c3

Question: What is the Company's valuation allowance against its U.S deferred tax assets as of December 31, 2019?

Target audit labels: answer_type=`span`, answer_from=`text`, operator=`span`, scale=``.

| Rank | Score | Case question | Answer type | Operator | Scale |
|---:|---:|---|---|---|---|
| 1 | 0.9198 | What was the Deferred tax assets, net of valuation allowance in 2019? | `span` | `span` | `thousand` |
| 2 | 0.9185 | What was the valuation allowance for deferred tax assets in 2020 and 2018 respectively? | `multi-span` | `multi_span` | `` |
| 3 | 0.9152 | What is the respective net increase in the valuation allowance for the years ended December 31, 2019 and 2018? | `multi-span` | `multi_span` | `` |
| 4 | 0.9116 | What was the valuation allowance maintained from fourth quarter of fiscal 2009 to the third quarter of fiscal 2018? | `span` | `span` | `` |

### tatqa:dev:6b289db7-2ee8-48ec-a257-e7e8f9640f1c

Question: What is the total assets for year 2019?

Target audit labels: answer_type=`span`, answer_from=`table`, operator=`span`, scale=`million`.

| Rank | Score | Case question | Answer type | Operator | Scale |
|---:|---:|---|---|---|---|
| 1 | 0.9026 | How much were the total assets during fiscal years 2018 and 2019, respectively? | `multi-span` | `multi_span` | `million` |
| 2 | 0.9012 | What was the total assets in 2015? | `span` | `span` | `thousand` |
| 3 | 0.9005 | What is the total assets as of November 30 2018? | `arithmetic` | `add` | `thousand` |
| 4 | 0.8954 | What was the difference between the total assets and goodwill from data and analytics? | `arithmetic` | `subtract` | `million` |

### tatqa:dev:81fc6048-7510-4c55-aa3c-4c9f1f5b8bcb

Question: What was the change in the servicing fee between 2018 and 2019?

Target audit labels: answer_type=`arithmetic`, answer_from=`table-text`, operator=`divide`, scale=`percent`.

| Rank | Score | Case question | Answer type | Operator | Scale |
|---:|---:|---|---|---|---|
| 1 | 0.9469 | What was the change in the transaction fees between 2017 and 2019? | `arithmetic` | `subtract` | `thousand` |
| 2 | 0.9417 | What was the change in the ending balance between 2017 and 2019? | `arithmetic` | `subtract` | `thousand` |
| 3 | 0.9409 | How much was the included change in fair value of the company's servicing asset included in its servicing fees? | `span` | `span` | `thousand` |
| 4 | 0.9356 | What was the percentage change in the term loan between 2018 and 2019? | `arithmetic` | `divide` | `percent` |

### tatqa:dev:f1eedc55-cc96-4574-b82b-e6f17cf176af

Question: What was the increase in interest income in 2019?

Target audit labels: answer_type=`span`, answer_from=`table-text`, operator=`span`, scale=``.

| Rank | Score | Case question | Answer type | Operator | Scale |
|---:|---:|---|---|---|---|
| 1 | 0.9597 | What was the reason for the increase in interest income in 2019? | `span` | `span` | `` |
| 2 | 0.9521 | What was the increase in interest income? | `span` | `span` | `` |
| 3 | 0.9442 | Why did interest and dividends income increase from $1,387 million in 2017 to $2,214 million in 2018? | `span` | `span` | `` |
| 4 | 0.9367 | What caused the increase in interest income and decrease in interest expense for the year ended 31 December 2019 respectively? | `multi-span` | `multi_span` | `` |

## Interpretation

This layer is ready for Strategy Memory design if downstream work treats these compatibility numbers as diagnostics, not selector features. The retriever can find cases with non-trivial answer-type/operator overlap without using target labels, and source exclusion prevents same-report/table reuse in the audit path.

Risks to carry forward:

- Case retrieval text uses relevant train paragraphs when available, while target queries use the full visible context. This matches the solved-case memory idea but creates mild representation asymmetry.
- `operator` is a coarse parser-derived audit label, not an official TAT-QA field.
- Scale compatibility is only a post-hoc diagnostic at this stage; it should not be used for retrieval tuning before a frozen protocol exists.

Decision: `READY FOR TAT-QA STRATEGY MEMORY DESIGN`.
