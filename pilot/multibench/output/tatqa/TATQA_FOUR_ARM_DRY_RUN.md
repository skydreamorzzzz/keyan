# TAT-QA Four-Arm Small Dry-Run

Date: 2026-08-16

Scope: one fixed 30-sample TAT-QA dev dry-run for pipeline validation. No prompt/retrieval/memory tuning, no router, no sample adjustment.

## Setup

- Sample: first 30 of fixed 120-sample strategy audit dev set, seed 20260816.
- Arms: none, case, strategy, both.
- Case retrieval: existing TAT-QA train Case Memory, top-4, source_id exclusion.
- Strategy retrieval: frozen HyDE query + frozen 30-item Strategy Memory, top-3.
- Runtime request: `{'provider': 'DeepSeek', 'backend': 'deepseek_openai_compatible', 'base_url': 'https://api.deepseek.com', 'requested_model': 'deepseek-v4-flash', 'effective_model': None, 'model_version': None, 'temperature': 0.0, 'max_tokens': 2500, 'thinking_mode': False}`; temperature=0; max_tokens=900; thinking disabled by client.
- Observed response models: `{'deepseek-v4-flash': 120}`; fingerprints: `{'a26a7955944dc5c60445bff77fac9c8e': 120}`.
- Execution cache records after run: 120; latest command API calls=0; cache hits=120. A cold run requires one execution call per sample-arm pair (30 x 4 = 120).
- Evaluator: project wrapper over official TAT-QA `TaTQAEmAndF1`.

## Four-Arm Metrics

| Arm | EM | F1 | Scale score | Parse failures | Invalid-scale parse errors |
|---|---:|---:|---:|---:|---:|
| `none` | 0.567 | 0.685 | 0.767 | 0 | 0 |
| `case` | 0.533 | 0.620 | 0.733 | 0 | 0 |
| `strategy` | 0.533 | 0.662 | 0.767 | 0 | 0 |
| `both` | 0.500 | 0.592 | 0.733 | 0 | 0 |

Best Fixed: `none` EM=0.567.
Sample Oracle EM=0.600.

## Memory Effect Events

- `case_only`: 0
- `strategy_only`: 1
- `none_only`: 0
- `both_only`: 0
- `none_gt_both`: 2
- `case_gt_both`: 1
- `strategy_gt_both`: 2

## By Answer Type

| Answer type | Arm | N | EM | F1 |
|---|---|---:|---:|---:|
| `arithmetic` | `none` | 7 | 0.714 | 0.714 |
| `arithmetic` | `case` | 7 | 0.571 | 0.571 |
| `arithmetic` | `strategy` | 7 | 0.714 | 0.714 |
| `arithmetic` | `both` | 7 | 0.571 | 0.571 |
| `count` | `none` | 1 | 1.000 | 1.000 |
| `count` | `case` | 1 | 1.000 | 1.000 |
| `count` | `strategy` | 1 | 0.000 | 0.000 |
| `count` | `both` | 1 | 0.000 | 0.000 |
| `multi-span` | `none` | 1 | 1.000 | 1.000 |
| `multi-span` | `case` | 1 | 1.000 | 1.000 |
| `multi-span` | `strategy` | 1 | 1.000 | 1.000 |
| `multi-span` | `both` | 1 | 1.000 | 1.000 |
| `span` | `none` | 21 | 0.476 | 0.646 |
| `span` | `case` | 21 | 0.476 | 0.600 |
| `span` | `strategy` | 21 | 0.476 | 0.660 |
| `span` | `both` | 21 | 0.476 | 0.608 |

## Typical Samples

- `tatqa:dev:03f232b9-a78e-42d0-b555-c801eaac577d` type=span scale=none correct=['strategy'] question=What was the amount of unrecognized stock-based compensation expense related to RSUs as of December 31, 2019? predictions={'none': {'answer': '$46.4 million', 'scale': 'million'}, 'case': {'answer': '$46.4 million', 'scale': 'million'}, 'strategy': {'answer': 46.4, 'scale': 'million'}, 'both': {'answer': '$46.4 million', 'scale': 'million'}}
- `tatqa:dev:40b0f371-bc5a-410e-a362-adcd32b2ed4e` type=span scale=none correct=['none', 'case', 'both'] question=What were the company's cash flows from operating activities influenced by? predictions={'none': {'answer': 'our growth, ability to maintain our contractual billing and collection terms, and our investments in headcount and infrastructure to support anticipated growth', 'scale': ''}, 'case': {'answer': ['our growth, ability to maintain our contractual billing and collection terms, and our investments in headcount and infrastructure to support anticipated growth'], 'scale': ''}, 'strategy': {'answer': 'growth, ability to maintain contractual billing and collection terms, and investments in headcount and infrastructure to support anticipated growth', 'scale': ''}, 'both': {'answer': 'our growth, ability to maintain our contractual billing and collection terms, and our investments in headcount and infrastructure to support anticipated growth', 'scale': ''}}
- `tatqa:dev:efb9abeb-ad8a-4558-9695-6d1054957e1b` type=arithmetic scale=million correct=['none', 'strategy'] question=What is the total income from continuing operations between 2017 to 2019? predictions={'none': {'answer': '$174.5', 'scale': 'million'}, 'case': {'answer': '174.5', 'scale': ''}, 'strategy': {'answer': '$174.5', 'scale': 'million'}, 'both': {'answer': '174.5', 'scale': ''}}
- `tatqa:dev:921426ff-bd1b-433c-886c-e38c4deaf900` type=count scale=none correct=['none', 'case'] question=How many years did Total services exceed $5,000 million? predictions={'none': {'answer': '2', 'scale': ''}, 'case': {'answer': '2', 'scale': ''}, 'strategy': {'answer': 1, 'scale': ''}, 'both': {'answer': 1, 'scale': ''}}

## Pipeline Notes

- Model outputs were parsed as JSON `answer` + `scale` before official evaluation.
- Strategy HyDE retrieval reused the frozen cached query-generation artifact; no strategy content or family was modified.
- Gold answer/type/scale/derivation were used only for evaluation and post-hoc reporting.

## Decision

Decision: `PROCEED`.
