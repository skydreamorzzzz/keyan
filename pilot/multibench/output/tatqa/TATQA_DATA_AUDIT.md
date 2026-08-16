# TAT-QA Data Audit

Date: 2026-08-16

Scope: data ingestion and schema audit only. No memory construction, no LLM calls, no four-arm experiment.

## Source

Raw data was downloaded from the official TAT-QA GitHub raw files linked by https://nextplusplus.github.io/TAT-QA/.
See `data/tatqa/SOURCE.md` for URLs, MD5 checksums, and license notes.

## Split Summary

| Split | Contexts | Questions | Gold answers missing | Derivation missing | Answer types |
|---|---:|---:|---:|---:|---|
| train | 2201 | 13215 | 0 | 6612 | `{'multi-span': 1645, 'span': 5722, 'arithmetic': 5543, 'count': 305}` |
| dev | 278 | 1668 | 0 | 834 | `{'span': 701, 'multi-span': 217, 'arithmetic': 718, 'count': 32}` |
| test | 278 | 1669 | 1669 | 1669 | `{'missing': 1669}` |

MD5 checks passed for all three downloaded files.

## Field Mapping

| Unified field | TAT-QA source | Notes |
|---|---|---|
| `dataset_id` | constant | `tatqa` |
| `sample_id` | `question.uid` | Prefixed as `tatqa:{split}:{uid}` |
| `question` | `questions[].question` | One flattened record per question |
| `text_context` | `paragraphs[].order/text` | Rendered as ordered paragraphs |
| `table` | `table.table` | Matrix of strings |
| `answer` | `questions[].answer` | Missing in public test |
| `operator` | answer type + derivation heuristic | Span/count from answer type; arithmetic uses derivation symbols when possible |
| `scale` | `questions[].scale` | Missing in public test |
| `derivation` | `questions[].derivation` | Empty for span/multi-span and absent in public test |
| `reasoning_annotation` | answer type/source, derivation, rel paragraphs, comparison flag | Raw annotation preserved |

## Missing / Anomaly Notes

- Public test has question-only records: no `answer`, `answer_type`, `answer_from`, `scale`, or `derivation`.
- Train/dev span and multi-span questions usually have empty derivation by design.
- `operator` is not a native TAT-QA field. The parser derives a coarse label from `answer_type`, `req_comparison`, and arithmetic symbols in `derivation`.
- `scale` is an empty string for no-scale answers in train/dev; it is `null` for public test records.
- The current parser keeps full paragraphs/table matrix in each flattened record. If storage becomes a concern, records can be normalized by context id later.

## Sanity Sample

A deterministic random sample of 20 train/dev records is saved to `data/tatqa/processed/tatqa_unified_sample20.json`.

| # | Split | Question | Answer | Operator | Scale | Derivation |
|---:|---|---|---|---|---|---|
| 1 | dev | What are the years included in the table? | `["2019", "2018"]` | `multi_span` | `` | `` |
| 2 | train | What years are included in the table? | `["2019", "2018", "2017"]` | `multi_span` | `` | `` |
| 3 | train | What was the change in deferred services revenue between 2018 and 2019? | `368` | `subtract` | `million` | `3,502-3,134` |
| 4 | train | Which years does the table provide information for the Company’s deferred tax assets and liabilities? | `["2019", "2018"]` | `multi_span` | `` | `` |
| 5 | train | What was the percentage change in the outstanding weighted-average exercise price per share for pivotal stock options be | `6.27` | `divide` | `percent` | `(8.31-7.82)/7.82` |
| 6 | dev | What does software and other revenue comprise of? | `["Comprised primarily of fees for end-user software products provided through direct customer"]` | `span` | `` | `` |
| 7 | train | What is the Total number of Shares purchased across the periods? | `["4,743,354"]` | `span` | `` | `` |
| 8 | train | What is the difference in percentage of revenues from FEI-NY between 2019 and 2018? | `8.5` | `subtract` | `percent` | `76.9-68.4` |
| 9 | train | What was the Net carrying amount of long-term debt in 2019? | `["206,909"]` | `span` | `thousand` | `` |
| 10 | train | How many Satellite subscribers were there in 2019? | `["1,005,282"]` | `span` | `` | `` |
| 11 | train | What is the average Total reclassifications for the period for the 3 years? | `-4.07` | `divide` | `million` | `-(2.5+1.9+7.8)/3` |
| 12 | train | Where are reclassifications related to gains and losses on available-for-sale debt securities included in? | `["Reclassifications related to gains and losses on available-for-sale debt securities are included in \"Interest and other expense, net\"."]` | `span` | `` | `` |
| 13 | train | What was the committed backlog in December 31, 2019? | `["$2,168"]` | `span` | `million` | `` |
| 14 | train | What is the percentage difference of Deposits and restricted cash for June 30, 2019 vs June 30, 2018? | `44.22` | `divide` | `percent` | `(13,671-9,479)/9,479` |
| 15 | train | What was the Weighted-average shares used in computing basic net income per share in 2019, 2018 and 2017 respectively? | `["74,994", "73,482", "72,292"]` | `multi_span` | `thousand` | `` |
| 16 | train | What was the Beginning balance in 2019 and 2018 respectively? | `["$6,164", "$4,931"]` | `multi_span` | `` | `` |
| 17 | dev | Why did normalised ROFE decrease? | `["Due to an increase in funds employed driven by refurbishments and acquisitions of hotels."]` | `span` | `` | `` |
| 18 | train | How are total segment assets defined? | `["accounts receivable, inventories, net, customer-related property, plant and equipment, intangible assets net of accumulated amortization and goodwill."]` | `span` | `` | `` |
| 19 | train | What is the average approximate Dollar Value of Shares that May Yet Be Purchased Under the Program from March 1, 2019 to | `7275.77` | `divide` | `million` | `(8,780.5+7,198.4+5,848.4) / 3 ` |
| 20 | train | For which year was  the  Total future minimum operating lease payments be higher? | `["2019"]` | `comparison` | `` | `Compare the  Total future minimum operating lease payments  for the larger value` |

## Next Step Toward Memory

Case Memory should store the flattened query, table, relevant paragraphs, answer type/source, scale, derivation, and raw reasoning annotation.
Strategy Memory should start only from train/dev records with executable or interpretable reasoning annotations: arithmetic derivations, counting derivations, and comparison flags.
Before any LLM experiments, add a TAT-QA evaluator wrapper using the official answer+scale metric.
