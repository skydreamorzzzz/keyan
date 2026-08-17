# TAT-QA Repeated-Run Stability

Date: 2026-08-17

Scope: repeated execution stability over the frozen 120-sample TAT-QA held-out diagnostic. rn1 is the existing held-out run; rn2/rn3 use independent execution cache namespaces. HyDE, retrieval, memory, prompt, runtime request, and canonicalized evaluator are frozen.

## Runtime / Cache

Note: the table below reports the latest command counters. After cache replay, calls are 0 and hits are 480; rn2/rn3 were first created in independent cold execution namespaces with 480 records each.

- `rn1` source `pilot/multibench/output/tatqa/tatqa_heldout_four_arm_diagnostic.json`; calls=0; hits=480; records=480; observed models `{'deepseek-v4-flash': 480}`; fingerprints `{'a26a7955944dc5c60445bff77fac9c8e': 480}`.
- `rn2` source `pilot/multibench/output/tatqa/tatqa_heldout_repeated_run_rn2_cache.jsonl`; calls=0; hits=480; records=480; observed models `{'deepseek-v4-flash': 480}`; fingerprints `{'a26a7955944dc5c60445bff77fac9c8e': 480}`.
- `rn3` source `pilot/multibench/output/tatqa/tatqa_heldout_repeated_run_rn3_cache.jsonl`; calls=0; hits=480; records=480; observed models `{'deepseek-v4-flash': 480}`; fingerprints `{'a26a7955944dc5c60445bff77fac9c8e': 480}`.

## Per-Run Four-Arm Metrics

| Run | Arm | EM | F1 | Parse failures | Normalization failures |
|---|---|---:|---:|---:|---:|
| `rn1` | `none` | 0.725 | 0.806 | 0 | 0 |
| `rn1` | `case` | 0.692 | 0.773 | 0 | 0 |
| `rn1` | `strategy` | 0.708 | 0.797 | 0 | 0 |
| `rn1` | `both` | 0.692 | 0.775 | 0 | 0 |
| `rn2` | `none` | 0.700 | 0.780 | 0 | 0 |
| `rn2` | `case` | 0.708 | 0.789 | 0 | 0 |
| `rn2` | `strategy` | 0.717 | 0.805 | 0 | 0 |
| `rn2` | `both` | 0.683 | 0.766 | 0 | 0 |
| `rn3` | `none` | 0.700 | 0.788 | 0 | 0 |
| `rn3` | `case` | 0.692 | 0.773 | 0 | 0 |
| `rn3` | `strategy` | 0.708 | 0.797 | 0 | 0 |
| `rn3` | `both` | 0.683 | 0.766 | 0 | 0 |

## Best Fixed / Expected Oracle

- Per-run Best Fixed arms: `{'rn1': 'none', 'rn2': 'strategy', 'rn3': 'strategy'}`.
- Mean per-run Best Fixed EM: 0.717.
- 3-run p_correct Best Fixed: `strategy` EM=0.711.
- 3-run p_correct Oracle EM=0.800.
- 3-run p_correct Oracle Gap=+0.089.
- Exclusive expected-best counts: `{'both_only_expected_best': 2, 'strategy_only_expected_best': 2, 'case_only_expected_best': 2, 'none_only_expected_best': 3}`.

## One-Shot Event Counts By Run

| Run | Case-only | Strategy-only | Both-only | None-only | None>Both | Case>Both | Strategy>Both |
|---|---:|---:|---:|---:|---:|---:|---:|
| `rn1` | 1 | 0 | 2 | 3 | 13 | 4 | 8 |
| `rn2` | 3 | 1 | 1 | 1 | 10 | 7 | 9 |
| `rn3` | 2 | 1 | 1 | 1 | 11 | 5 | 9 |

## Preference-Event Stability

| Event | Any run | >=2/3 runs | 3/3 runs |
|---|---:|---:|---:|
| `none_gt_both` | 13 | 12 | 9 |
| `case_gt_both` | 7 | 5 | 4 |
| `strategy_gt_both` | 10 | 9 | 7 |

## Correctness Flip Rate

| Arm | Query flip count | Query flip rate | Pairwise disagreement rate |
|---|---:|---:|---:|
| `none` | 4 | 0.033 | 0.022 |
| `case` | 2 | 0.017 | 0.011 |
| `strategy` | 5 | 0.042 | 0.028 |
| `both` | 3 | 0.025 | 0.017 |

Mean query-arm flip rate: 0.029.

## Interpretation

- Overall arm correctness is noisy across single executions, so one-shot event counts should not be read as stable selector labels.
- The p_correct oracle measures repeated-run expected heterogeneity under the frozen runtime and canonicalized evaluator.
- Preference-event stability focuses on selector-relevant deviations from Both, especially None/Case/Strategy outperforming Both.

## Decision

Decision: `TAT-QA HETEROGENEITY STABLE`.
