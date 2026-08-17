# MultiHiertt Four-Arm Dry-Run — Stage 33

Date: 2026-08-18

## Setup

- Sample: first 60 of fixed 120-sample validation set (seed 20260817).
- Arms: none, case, strategy, both.
- Case retrieval: full-context query, top-4, source_id exclusion.
- Strategy retrieval: question-only query + family-dedup top-3 from k=10 (Stage 32 protocol).
- Runtime: `deepseek_openai_compatible` / `deepseek-v4-flash`, temp=0, max_tokens=1400.
- Observed response models: {'deepseek-v4-flash': 240}.
- Runtime guard: `{'expected': {'backend': 'deepseek_openai_compatible', 'base_url': 'https://api.deepseek.com', 'requested_model': 'deepseek-v4-flash', 'response_model': 'deepseek-v4-flash', 'thinking_mode': False}, 'namespace_fingerprint': 'a26a7955944dc5c60445bff77fac9c8e'}`.
- Response format: `{'type': 'json_object'}`.
- Execution cache: `pilot/multibench/output/multihiertt/multihiertt_four_arm_dry_run_repaired_cache.jsonl`.
- API calls=0; cache hits=240.
- Diagnostic parse retry records: 32 (not counted as successful cache records).

## Four-Arm Metrics

| Arm | EM | F1 | Parse failures |
|---|---:|---:|---:|
| `none` | 0.117 | 0.125 | 0 |
| `case` | 0.200 | 0.208 | 0 |
| `strategy` | 0.183 | 0.192 | 0 |
| `both` | 0.233 | 0.242 | 0 |

Best Fixed: `both` EM=0.233.
Oracle EM=0.250.  Oracle Gap=0.017.

## Retrieval-Conditioned Analysis

- Strategy family hit (gold family in top-3 dedup): 42/60

| Arm | EM on hit | EM on miss | EM overall |
|---|---:|---:|---:|
| `none` | 0.119 | 0.111 | 0.117 |
| `case` | 0.143 | 0.333 | 0.200 |
| `strategy` | 0.119 | 0.333 | 0.183 |
| `both` | 0.167 | 0.389 | 0.233 |

Interpretation guideline:
- Strategy EM on hit > None EM on hit → strategy helps when retrieved correctly.
- Strategy EM on miss < None EM on miss → strategy causes interference when retrieval fails.

## Memory Effect Events

- `case_only`: 1
- `strategy_only`: 0
- `none_only`: 0
- `both_only`: 1
- `none_gt_both`: 0
- `case_gt_both`: 1
- `strategy_gt_both`: 0

## By Answer Type

| Type | N | none EM | case EM | strategy EM | both EM |
|---|---:|---:|---:|---:|---:|
| program | 53 | 0.094 | 0.170 | 0.151 | 0.208 |
| span    | 7 | 0.286 | 0.429 | 0.429 | 0.429 |

## Sample Records (interesting: not all-correct or all-wrong)

- uid=25fa7222665c4740ba34eaddf3769ff5 type=program gold=program:aggregation_sum hit=True correct=['strategy', 'both'] Q: What is the amount of Commercial and Commercial realestate in the years with the least Commercial for Gross Charge-offs 
  preds: {'none': '2017', 'case': 24, 'strategy': 210, 'both': 210}
- uid=0565d8b781a14a29852db42ceaf3644e type=program gold=program:division_composition hit=True correct=['both'] Q: what is the money pool activity use of operating cash flows as a percentage of receivables from the money pool in 2003?
  preds: {'none': '63.0%', 'case': 63.0, 'strategy': 63.0, 'both': 0.6296}
- uid=a0e6c373d5e545c487ad1ae2b3027259 type=program gold=program:difference_then_ratio hit=False correct=['case', 'both'] Q: what is the roi of an investment in s&p500 index from 2011 to 2012?
  preds: {'none': 16.0, 'case': 0.16, 'strategy': 16.0, 'both': 0.16}
- uid=7389cfa35a894e14bf0773e29d326973 type=program gold=program:aggregation_sum hit=True correct=['none', 'case', 'both'] Q: What's the sum of Debt maturities of Thereafter, and Capital lease obligations of Less than 1 year ?
  preds: {'none': 6905, 'case': 6905, 'strategy': 2527, 'both': 6905}
- uid=2c5ade1a88b84b07b6e534a544862161 type=span gold=span:comparison_yesno hit=False correct=['case', 'strategy', 'both'] Q: Does the average value of Loans and leases in 2014 greater than that in 2013
  preds: {'none': 'No', 'case': 'Yes', 'strategy': 'Yes', 'both': 'Yes'}
- uid=36db2cbbf36640aa9ffebe6bb2013981 type=program gold=program:change_rate hit=True correct=['case'] Q: what was the growth in the account balance in 2017
  preds: {'none': '$138', 'case': 0.9857142857142857, 'strategy': 138, 'both': 138}
- uid=d59dd32fccc5468ab10a15cf07cc65d7 type=program gold=program:aggregation_sum hit=False correct=['case', 'strategy', 'both'] Q: What is the total amount of Insurance of At December 31, 2017 Case Reserves, and Insurance of At December 31, 2016 Case 
  preds: {'none': ['$1,049.4', '$1,018.5'], 'case': 2067.9, 'strategy': 2067.9, 'both': 2067.9}
- uid=77a0b4dbe903419399b79b1e026f1fae type=program gold=program:difference hit=False correct=['case', 'strategy', 'both'] Q: what is the mathematical range for average train speed ( mph ) for 2008-2010?
  preds: {'none': '23.5-26.2', 'case': 3.8, 'strategy': 3.8, 'both': 3.8}
- uid=87db6a9c0c874dc4ba00221006d105b1 type=program gold=program:difference_composition hit=False correct=['strategy', 'both'] Q: what was the total amount lost from the bond authorization to the withdrawn?
  preds: {'none': '$13.0 million', 'case': 'The total amount lost from the bond authorization to the withdrawn is the sum of the differences between the authorized amounts and the amounts drawn for each bond. For Franklin, Kentucky: $54.0 - $51.8 = $2.2 million. For Macon, Georgia: $58.0 - $49.9 = $8.1 million. For Brentwood, Tennessee: $78.0 - $75.3 = $2.7 million. Summing these: $2.2 + $8.1 + $2.7 = $13.0 million.', 'strategy': 13.0, 'both': 13.0}

## Decision

`FIX PIPELINE FIRST`

Execution/cache/provenance layer is repaired, but absolute EM remains low and the 60-sample oracle gap is only 1/60; run context/prompt/evaluator audit before repeated-run expansion.
