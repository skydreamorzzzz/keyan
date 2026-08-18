# MultiHiertt Four-Arm Dry-Run — Stage 33

Date: 2026-08-17

## Setup

- Sample: first 4 of fixed 120-sample validation set (seed 20260817).
- Arms: none, case, strategy, both.
- Case retrieval: full-context query, top-4, source_id exclusion.
- Strategy retrieval: question-only query + family-dedup top-3 from k=10 (Stage 32 protocol).
- Runtime: `deepseek_openai_compatible` / `deepseek-v4-flash`, temp=0, max_tokens=1400.
- Observed response models: {'deepseek-v4-flash': 16}.
- Runtime guard: `{'expected': {'backend': 'deepseek_openai_compatible', 'base_url': 'https://api.deepseek.com', 'requested_model': 'deepseek-v4-flash', 'response_model': 'deepseek-v4-flash', 'thinking_mode': False}, 'namespace_fingerprint': 'a26a7955944dc5c60445bff77fac9c8e'}`.
- Response format: `{'type': 'json_object'}`.
- Execution cache: `pilot/multibench/output/multihiertt/multihiertt_four_arm_dry_run_repaired_smoke_cache.jsonl`.
- API calls=1; cache hits=15.

## Four-Arm Metrics

| Arm | EM | F1 | Parse failures |
|---|---:|---:|---:|
| `none` | 0.250 | 0.250 | 0 |
| `case` | 0.250 | 0.250 | 0 |
| `strategy` | 0.250 | 0.250 | 0 |
| `both` | 0.250 | 0.250 | 0 |

Best Fixed: `none` EM=0.250.
Oracle EM=0.250.  Oracle Gap=0.000.

## Retrieval-Conditioned Analysis

- Strategy family hit (gold family in top-3 dedup): 3/4

| Arm | EM on hit | EM on miss | EM overall |
|---|---:|---:|---:|
| `none` | 0.333 | 0.000 | 0.250 |
| `case` | 0.333 | 0.000 | 0.250 |
| `strategy` | 0.333 | 0.000 | 0.250 |
| `both` | 0.333 | 0.000 | 0.250 |

Interpretation guideline:
- Strategy EM on hit > None EM on hit → strategy helps when retrieved correctly.
- Strategy EM on miss < None EM on miss → strategy causes interference when retrieval fails.

## Memory Effect Events

- `case_only`: 0
- `strategy_only`: 0
- `none_only`: 0
- `both_only`: 0
- `none_gt_both`: 0
- `case_gt_both`: 0
- `strategy_gt_both`: 0

## By Answer Type

| Type | N | none EM | case EM | strategy EM | both EM |
|---|---:|---:|---:|---:|---:|
| program | 3 | 0.000 | 0.000 | 0.000 | 0.000 |
| span    | 1 | 1.000 | 1.000 | 1.000 | 1.000 |

## Sample Records (interesting: not all-correct or all-wrong)

- uid=6e69e996da0a482b87e237352da9369b type=program gold=program:difference hit=False correct=[] Q: What is the sum of Investment real estate in 2012 and Gain (loss) recognized in OCI on derivatives in 2011? (in million)
  preds: {'none': 3193, 'case': 3193, 'strategy': 3193, 'both': 3193}
- uid=c649cb8dafee4d23b4184b0c8c89e74f type=program gold=program:change_rate hit=True correct=[] Q: In the year with the most Interest cost in Table 1, what is the growth rate of Environmental in Table 0?
  preds: {'none': -0.2318840579710145, 'case': 0.0, 'strategy': -0.2318840579710145, 'both': 0.0}
- uid=faac106d01bb414e8459e88d762e51b4 type=span gold=span:superlative_lookup hit=True correct=['none', 'case', 'strategy', 'both'] Q: What's the greatest value of Stores Opened in 2011?
  preds: {'none': 86, 'case': 86, 'strategy': 86, 'both': 86}
- uid=776342a2d8c1492286eedc213289f373 type=program gold=program:change_rate hit=True correct=[] Q: In the year with the most Granted for shares(in thousands), what is the growth rate of Outstanding ? (in %)
  preds: {'none': 'N/A', 'case': '-17.87', 'strategy': 0.0, 'both': 0.0}
