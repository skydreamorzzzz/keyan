# Stage 3 Stability / Validity Audit

Date: 2026-08-16

Scope: fix execution-label validity, repair Stage 2 cache provenance, and test whether the oracle gap reflects cross-run marginal-utility heterogeneity rather than one-shot noise. No new selector features or router design were added.

## Artifacts

- Strict evaluator audit: `pilot/stage3/evaluator_audit.json`
- Rebuilt strict oracle dataset: `pilot/stage3/oracle_analysis_dataset.json[l]`
- Stability runs: `pilot/stage3/stability/stability_run_r1.json`, `stability_run_r2.json`
- Stability analysis: `pilot/stage3/stability/stability_analysis.json`
- One-shot event stability: `pilot/stage3/stability/one_shot_event_stability.json`
- Duplicate audit: `pilot/stage3/duplicate_audit.json`
- CV leakage audit: `selector_baselines_strict_random.json`, `selector_baselines_strict_group_report.json`

## 1. Strict Official Execution Evaluator

`pilot/executor.py` now uses official-compatible execution equality for the main `match_result`: numeric predictions and gold execution answers are rounded to 5 decimals and compared by exact equality, matching `analysis/official_code/evaluate.py`. The previous relative-tolerance evaluator is preserved as `match_result_legacy` for diagnostics only.

The executor also fixes parsing of official linear programs with comma-separated top-level steps and no `#` separator, such as `subtract(...), divide(...)`. Gold-program tests now compare local execution with the official evaluator on FinQA dev/train slices.

Gold-program audit:

- dev: 883/883 official gold programs match local execution
- train: 6251/6251 official gold programs match local execution
- local-vs-official checked mismatches: 0

Stage 2 strict recomputation changes the absolute full-doc accuracies by about -0.2pp vs the old relative-tolerance labels, but the oracle gap is unchanged.

Full-doc, strict:

| Arm | Accuracy |
|---|---:|
| None | 0.6809 |
| Case | 0.7175 |
| Strategy | 0.6931 |
| Both | 0.7256 |
| Best Fixed | 0.7256 |
| Oracle | 0.8191 |
| Oracle Gap | 0.0935 |

Old legacy full-doc:

- Best Fixed: 0.7276
- Oracle: 0.8211
- Oracle Gap: 0.0935

Structured, strict:

- None 0.6220, Case 0.6443, Strategy 0.6301, Both 0.6545
- Best Fixed 0.6545, Oracle 0.7378, Oracle Gap 0.0833

## 2. Cache Provenance Fix

`pilot/stage2_official/run_official.py` no longer keys cache entries by `prompt[:300]`. The new key hashes:

- full system prompt
- full user prompt
- mode
- arm
- sample index
- model/config fields
- cache-key version

The new stability experiment uses independent cache namespaces under `pilot/stage3/stability/llm_cache_stability_<replicate>.jsonl`, so it does not reuse Stage 2 cache content.

Provenance caveat: the old Stage 2 run remains a historical replicate whose original cache key was weak. The two new replicates were run after the cache fix using the current available DeepSeek official API fallback (`deepseek-chat`, temperature 0). This is not byte-identical to the prior Anthropic-compatible `DeepSeek-V4-flash[1m]` backend, so stability conclusions should be treated as strong evidence of run-level structure but not as a perfect same-backend reproducibility proof.

## 3. Repeated-Run Stability

Sample: deterministic 250 of official dev[:492], selected by sorting SHA-256 of `stage3-stability-v1|{sample_index}|{sample_id}`. This selection is independent of existing correctness labels.

Replicates analyzed: `stage2_old`, `r1`, `r2`.

Per-arm cross-run correctness agreement:

| Arm | Agreement |
|---|---:|
| None | 0.9387 |
| Case | 0.9547 |
| Strategy | 0.9360 |
| Both | 0.9627 |

One-shot event stability, using `stage2_old` events as the base:

| Event | old count | in >=1 new run | in both new runs |
|---|---:|---:|---:|
| Case > Strategy | 22 | 11 | 10 |
| Strategy > Case | 14 | 10 | 8 |
| Case > Both negative interference | 7 | 3 | 3 |
| Strategy > Both negative interference | 6 | 3 | 2 |

Across any replicate, sign stability among queries where the event appeared at least once:

- Case > Strategy: 20/33 stable in at least 2 runs
- Strategy > Case: 18/24 stable in at least 2 runs
- Case > Both negative interference: 4/9 stable in at least 2 runs
- Strategy > Both negative interference: 11/15 stable in at least 2 runs

The marginal-utility signs are not pure noise. Strategy-favoring events are more stable than Case-favoring events in this sample; Case-vs-Both negative interference is the least stable.

## 4. One-Shot vs Expected Oracle Gap

On the 250-query stability subset:

| Replicate | Best Fixed | Oracle | Gap |
|---|---:|---:|---:|
| stage2_old | 0.748 | 0.832 | 0.084 |
| r1 | 0.748 | 0.836 | 0.088 |
| r2 | 0.744 | 0.836 | 0.092 |

Repeated-run expected accuracies:

| Arm | Expected accuracy |
|---|---:|
| None | 0.6947 |
| Case | 0.7227 |
| Strategy | 0.7053 |
| Both | 0.7467 |
| Expected Oracle | 0.8347 |
| Expected Oracle Gap | 0.0880 |

The one-shot gap and repeated expected gap are close. On this subset, the expected oracle gap is 8.8pp, compared with the full 492 strict gap of 9.35pp. That argues against the oracle gap being mostly one-shot run noise.

## 5. Cross-Run Preference Transfer

Protocol: for each held-out run, use the other two runs to choose the best arm per query, then evaluate that choice on the held-out run. Ties use the training-run global best arm.

| Held-out run | Selector acc. | Held-out Best Fixed | Delta |
|---|---:|---:|---:|
| stage2_old | 0.792 | 0.748 | +0.044 |
| r1 | 0.832 | 0.748 | +0.084 |
| r2 | 0.828 | 0.744 | +0.084 |
| Mean | 0.817 | 0.747 | +0.071 |

Cross-run preferences do transfer. The mean transfer gain recovers about 80% of the repeated expected oracle gap on the 250-query subset: `0.0707 / 0.0880`.

This is the strongest evidence in this audit that the oracle gap contains stable query-level heterogeneity.

## 6. Report-Grouped CV Audit

Stage 3 random KFold is optimistic because report siblings can cross folds. I added `--cv group_report` to `run_selector_baselines.py`.

Strict full-doc selector best results:

| CV | Best model | Accuracy | Improvement vs Best Fixed | Gap Recovery |
|---|---|---:|---:|---:|
| random KFold | query_retrieval_meta/logreg | 0.7500 | +0.0244 | 0.2609 |
| GroupKFold by report | query_retrieval_meta/rf | 0.7317 | +0.0061 | 0.0652 |

The prior selector conclusion should be weakened: query/retrieval metadata features can still beat Best Fixed slightly under grouped evaluation, but the gain is much smaller than random KFold suggested.

## 7. Exact Duplicate Robustness

Definition: lowercase whitespace-normalized exact question match between official dev[:492] and train.

- duplicate dev queries: 9/492
- duplicate indices: 94, 103, 125, 226, 364, 387, 406, 416, 459
- stability subset duplicates: 6/250

Full 492, strict:

- None 0.6809, Case 0.7175, Strategy 0.6931, Both 0.7256
- Case gain vs None: +3.66pp
- Oracle Gap: 9.35pp

After duplicate removal, n=483:

- None 0.6770, Case 0.7143, Strategy 0.6915, Both 0.7226
- Case gain vs None: +3.73pp
- Oracle Gap: 9.52pp

Exact duplicates do not explain the Case gain or the oracle gap.

## Answers

1. Strict official evaluator changes Stage 2 absolute full-doc numbers slightly downward: Best Fixed 0.7276 -> 0.7256, Oracle 0.8211 -> 0.8191. Oracle Gap remains 9.35pp.
2. One-shot marginal preference events are partially stable. In the 250-query subset, 10/22 historical Case>Strategy and 8/14 historical Strategy>Case events recur in both new runs; negative interference is real but less uniformly stable.
3. Cross-run preference transfer exceeds held-out Best Fixed by +7.1pp on average, recovering about 80% of the repeated expected oracle gap on the stability subset.
4. The 9pp Oracle Gap is not mostly run noise. A practical estimate is roughly 7pp stable transferable heterogeneity and about 1-2pp residual noise/untapped heterogeneity under this simple cross-run oracle-transfer protocol.
5. Report-grouped CV materially weakens Stage 3 selector claims: best strict random CV accuracy 0.7500 drops to 0.7317 under GroupKFold.
6. Exact duplicate removal does not remove Case gain: Case vs None is +3.73pp without duplicates, slightly larger than the full-sample +3.66pp.

Final decision: **PROCEED TO MARGINAL-UTILITY SELECTOR**

Reason: evaluator validity is repaired, duplicate leakage does not explain the effect, and cross-run preference transfer shows stable per-query marginal utility. The next selector should be evaluated under strict official labels, report-grouped CV, and repeated-run preference stability; it should not rely on the optimistic random-KFold numbers.
