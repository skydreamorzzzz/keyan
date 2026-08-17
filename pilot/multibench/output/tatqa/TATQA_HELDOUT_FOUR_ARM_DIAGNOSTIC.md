# TAT-QA Held-Out Four-Arm Diagnostic

Date: 2026-08-17

Scope: fresh held-out TAT-QA dev diagnostic. One run per sample-arm. No prompt/retrieval/memory/sample tuning.

## Setup

- Sample: 120 dev samples drawn with seed `20260817` from dev after excluding the prior Strategy retrieval audit set (120 samples, seed `20260816`).
- Candidate pool after exclusion: 1548 / 1668.
- Arms: none, case, strategy, both.
- Case retrieval: top-4 existing TAT-QA train Case Memory with source_id exclusion.
- Strategy retrieval: frozen HyDE + top-3 frozen Strategy Memory.
- Evaluation: canonicalized TAT-QA prediction contract from TATQA_OUTPUT_NORMALIZATION_AUDIT.md.
- Runtime request: `{'provider': 'DeepSeek', 'backend': 'deepseek_openai_compatible', 'base_url': 'https://api.deepseek.com', 'requested_model': 'deepseek-v4-flash', 'effective_model': None, 'model_version': None, 'temperature': 0.0, 'max_tokens': 2500, 'thinking_mode': False}`; observed models `{'deepseek-v4-flash': 480}`; fingerprints `{'a26a7955944dc5c60445bff77fac9c8e': 480}`.
- HyDE cache/API: calls=0, hits=120, records_after=239.
- Execution cache/API: calls=0, hits=480, records_after=480.
- Cold-run call budget: at most 120 HyDE generation calls plus 480 execution calls; latest reported calls are from the cache-replay command.
- Normalization changed predictions: 141 / 480.

## Four-Arm Metrics

| Arm | EM | F1 | Scale score | Parse failures | Invalid scale | Normalization failures |
|---|---:|---:|---:|---:|---:|---:|
| `none` | 0.725 | 0.806 | 0.925 | 0 | 0 | 0 |
| `case` | 0.692 | 0.773 | 0.925 | 0 | 0 | 0 |
| `strategy` | 0.708 | 0.797 | 0.900 | 0 | 0 | 0 |
| `both` | 0.692 | 0.775 | 0.925 | 0 | 0 | 0 |

Best Fixed: `none` EM=0.725.
Sample Oracle EM=0.808.
Oracle Gap=+0.083.

## Memory Effect Events

- `case_only`: 1
- `strategy_only`: 0
- `both_only`: 2
- `none_only`: 3
- `none_gt_both`: 13
- `case_gt_both`: 4
- `strategy_gt_both`: 8

## By Answer Type

| Answer type | Arm | N | EM | F1 |
|---|---|---:|---:|---:|
| `arithmetic` | `none` | 45 | 0.711 | 0.711 |
| `arithmetic` | `case` | 45 | 0.689 | 0.689 |
| `arithmetic` | `strategy` | 45 | 0.711 | 0.711 |
| `arithmetic` | `both` | 45 | 0.711 | 0.711 |
| `count` | `none` | 3 | 1.000 | 1.000 |
| `count` | `case` | 3 | 0.000 | 0.000 |
| `count` | `strategy` | 3 | 0.667 | 0.667 |
| `count` | `both` | 3 | 0.000 | 0.000 |
| `multi-span` | `none` | 12 | 0.833 | 0.898 |
| `multi-span` | `case` | 12 | 0.917 | 0.982 |
| `multi-span` | `strategy` | 12 | 0.833 | 0.898 |
| `multi-span` | `both` | 12 | 0.917 | 0.982 |
| `span` | `none` | 60 | 0.700 | 0.849 |
| `span` | `case` | 60 | 0.683 | 0.832 |
| `span` | `strategy` | 60 | 0.683 | 0.848 |
| `span` | `both` | 60 | 0.667 | 0.819 |

## Typical Non-Uniform Samples

- `tatqa:dev:bbb9ab37-568a-4bab-9b95-cb3c43c5baa1` type=multi-span scale=none correct=['case', 'strategy', 'both'] question=Which years does the table show? predictions={'none': {'answer': ['December 31, 2019', 'December 31, 2018'], 'scale': ''}, 'case': {'answer': ['2019', '2018'], 'scale': ''}, 'strategy': {'answer': ['2019', '2018'], 'scale': ''}, 'both': {'answer': ['2019', '2018'], 'scale': ''}}
- `tatqa:dev:da716abd-9641-4038-8f1d-4233fcf405ee` type=arithmetic scale=percent correct=['both'] question=What is the percentage change in the long-lived assets in United States from 2018 to 2019? predictions={'none': {'answer': '18.95%', 'scale': 'percent'}, 'case': {'answer': 18.95, 'scale': 'percent'}, 'strategy': {'answer': 18.95, 'scale': 'percent'}, 'both': {'answer': 18.94, 'scale': 'percent'}}
- `tatqa:dev:568f039b-5753-4e91-b3aa-17cbcbe9b259` type=arithmetic scale=million correct=['none', 'case'] question=What was the change in the Pre-contract costs from 2018 to 2020? predictions={'none': {'answer': '-35', 'scale': 'million'}, 'case': {'answer': '-35', 'scale': 'million'}, 'strategy': {'answer': 35, 'scale': 'million'}, 'both': {'answer': 35, 'scale': 'million'}}
- `tatqa:dev:75cadcb4-da5e-4e3e-b2ad-36a31be3d013` type=span scale=none correct=['none', 'strategy'] question=How were operating segments defined as? predictions={'none': {'answer': 'components of an enterprise for which separate financial information is evaluated regularly by the chief operating decision maker in deciding how to allocate resources and assessing performance', 'scale': ''}, 'case': {'answer': ['Operating segments are defined as components of an enterprise for which separate financial information is evaluated regularly by the chief operating decision maker in deciding how to allocate resources and assessing performance.'], 'scale': ''}, 'strategy': {'answer': 'components of an enterprise for which separate financial information is evaluated regularly by the chief operating decision maker in deciding how to allocate resources and assessing performance', 'scale': ''}, 'both': {'answer': 'Operating segments are defined as components of an enterprise for which separate financial information is evaluated regularly by the chief operating decision maker in deciding how to allocate resources and assessing performance.', 'scale': ''}}
- `tatqa:dev:58d97328-c6a8-4f7e-9740-80c0384306fb` type=span scale=none correct=['case'] question=What are the sources of additional liquidity? predictions={'none': {'answer': ['maintaining an adequate cash balance', 'access to global funding sources', 'committed global credit facilities', 'other committed and uncommitted lines of credit worldwide'], 'scale': ''}, 'case': {'answer': 'maintaining an adequate cash balance, access to global funding sources, committed global credit facilities and other committed and uncommitted lines of credit worldwide', 'scale': ''}, 'strategy': {'answer': ['maintaining an adequate cash balance', 'access to global funding sources', 'committed global credit facilities', 'other committed and uncommitted lines of credit worldwide'], 'scale': ''}, 'both': {'answer': ['maintaining an adequate cash balance', 'access to global funding sources', 'committed global credit facilities', 'other committed and uncommitted lines of credit worldwide'], 'scale': ''}}
- `tatqa:dev:0cca40eb-3b7e-4ea2-83b0-c6be83190b12` type=arithmetic scale=percent correct=['strategy', 'both'] question=What is the percentage increase / (decrease) in average Urner Barry Spot Egg Market Quotations 1 in 2019 compared to 2018? predictions={'none': {'answer': '-17.4%', 'scale': 'percent'}, 'case': {'answer': '-17.4%', 'scale': 'percent'}, 'strategy': {'answer': '-17.45', 'scale': 'percent'}, 'both': {'answer': '-17.45', 'scale': 'percent'}}
- `tatqa:dev:e35b10e8-fe97-4cc4-b59e-cbeb0679f6c7` type=span scale=thousand correct=['none', 'case'] question=What is the Balance at the beginning of the fiscal year for 2019? predictions={'none': {'answer': '$1,264', 'scale': 'thousand'}, 'case': {'answer': '$1,264', 'scale': 'thousand'}, 'strategy': {'answer': '$1,264', 'scale': ''}, 'both': {'answer': '$1,264', 'scale': ''}}
- `tatqa:dev:0c1736a6-bc48-4250-81da-d0ca69d28918` type=span scale=none correct=['none', 'strategy'] question=What was the federal state income tax in fiscal year 2019? predictions={'none': {'answer': '$36.5 million', 'scale': 'million'}, 'case': {'answer': '$15,743', 'scale': 'thousand'}, 'strategy': {'answer': 36.5, 'scale': 'million'}, 'both': {'answer': '$15,743', 'scale': 'thousand'}}
- `tatqa:dev:af294acf-0db4-4248-9dcb-d7f53d1f0687` type=span scale=thousand correct=['case', 'strategy', 'both'] question=What were the total assets in 2017? predictions={'none': {'answer': '$669,094', 'scale': ''}, 'case': {'answer': '$669,094', 'scale': 'thousand'}, 'strategy': {'answer': '$669,094', 'scale': 'thousand'}, 'both': {'answer': '$669,094', 'scale': 'thousand'}}
- `tatqa:dev:8757782d-306d-4a0d-b22e-ab0f2b58171c` type=span scale=thousand correct=['strategy', 'both'] question=What was the Total other (expense) income, net in 2017? predictions={'none': {'answer': '$1,758', 'scale': ''}, 'case': {'answer': '$1,758', 'scale': ''}, 'strategy': {'answer': '$1,758', 'scale': 'thousand'}, 'both': {'answer': '$1,758', 'scale': 'thousand'}}

## Decision

Decision: `PROCEED TO REPEATED RUNS`.
