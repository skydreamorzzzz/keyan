# Stage 4A — Marginal-Utility Learnability Audit

Date: 2026-08-16

Question: using only inference-time observable state, can we predict whether a new query/new annual report should deviate from default Both?

This audit treats the prior +8.9pp transfer result as a **same-query repeated-history ceiling**, not as an unseen-query selector result.

## 1. Target Definition

Default action: `Both`.

For each deviation arm `a in {none, case, strategy}` and query `i`, targets use strict same-runtime replicates `rn1/rn2/rn3`:

```text
delta_a(i) = mean_r[correct(i,a,r) - correct(i,both,r)]
gain_a(i) = P_r(a correct AND both wrong)
harm_a(i) = P_r(a wrong AND both correct)
net_utility_a(i) = gain_a(i) - harm_a(i)
```

The core target is relative marginal utility, not whether an arm is correct by itself.

Artifacts:

- `marginal_utility_dataset.jsonl`
- `support_audit.json`
- `synthetic_features.jsonl`
- `marginal_baselines_annual.json`
- `marginal_baselines_page.json`

## 2. Annual-Report Grouping Audit

Grouping was tightened:

- `page_group`: e.g. `RL/2012/page_13.pdf`
- `annual_report_group`: e.g. `RL/2012`

Main results use GroupKFold by annual report. Page grouping is secondary only.

Dataset:

- n = 250 runtime-normalized stability subset queries
- annual-report groups = 158
- page groups = 187

## 3. Stable Deviation Support

Deviation events are sparse but not concentrated in a single report.

| Deviation | any run | >=2/3 runs | 3/3 runs | reports with any | max report share |
|---|---:|---:|---:|---:|---:|
| None > Both | 18 | 18 | 17 | 18 | 0.056 |
| Case > Both | 6 | 5 | 5 | 6 | 0.167 |
| Strategy > Both | 12 | 12 | 10 | 12 | 0.083 |

Any deviation event:

- 24/250 queries
- 22 annual reports
- top reports have only 2 events each

Overlap:

- None + Strategy: 8 queries
- Case + None: 3 queries
- Case + Strategy: 1 query

Support judgment: there is enough signal to audit learnability, but not enough positive support for confident method claims. Case > Both is especially data-limited.

## 4. Existing-Feature Baseline

Inference-safe existing features include query lexical/structural flags, retrieval scores/margins/entropy/disagreement, and retrieved-memory embeddings. Fields containing `gold`, `oracle`, `correct`, `preferred`, or labels are excluded from Stage 4A features.

Annual-report GroupKFold, nested threshold selection:

| Feature set | Formulation/model | Accuracy | Gain vs Both | Coverage | Cluster 95% CI |
|---|---|---:|---:|---:|---:|
| existing_meta | delta/ridge | 0.7507 | +0.0040 | 0.156 | [-0.0113, 0.0201] |
| existing_all | best | 0.7400 | -0.0067 | 0.036 | [-0.0175, 0.0000] |

Existing features alone do not provide reliable unseen-query routing.

## 5. Synthetic Feature Design

Generated one fixed-schema DeepSeek feature record per query. The generator sees only:

- current question and inference-time context
- retrieved cases
- retrieved strategies

It does not see correctness labels, gold answer, gold program, oracle set, or gold operation annotations.

Runtime:

- requested/effective model: `deepseek-v4-flash`
- system fingerprint: `a26a7955944dc5c60445bff77fac9c8e`
- temperature: 0
- fixed JSON schema, 20 numeric mechanism features

Mechanism groups:

- Scale: output scale, unit risk, case/strategy scale compatibility
- Compatibility: operation family likelihood, arithmetic depth, case/strategy applicability and operation compatibility
- Interaction: ambiguity, copy risk, strategy conflict, case-strategy agreement, overload risk

This feature idea is exploratory: it was designed after observing Stage 3/3.1 failure modes, especially scale pollution and memory conflict.

## 6. Leakage Audit

Controls:

- outer GroupKFold by annual report
- inner GroupKFold on train folds only for threshold/lambda selection
- no test-fold prior, threshold, label, or statistic enters training
- synthetic features are generated from inference-visible state only
- synthetic cache key includes full input, schema, runtime, model, endpoint, and prompt
- runtime guard aborts if response model/fingerprint changes within one namespace

## 7. Marginal Regression Result

Best annual-report grouped result:

| Feature set | Model | Accuracy | Gain vs Both | Gap Recovery | Coverage | Precision | Harm rate | Cluster 95% CI |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| existing_meta + compatibility | ridge | 0.7640 | +0.0173 | 0.188 | 0.208 | 0.154 | 0.077 | [-0.0092, 0.0449] |

Details:

- Always Both: 0.7467
- Oracle: 0.8387
- deviation count: 52/250
- beneficial deviations: 8
- harmful deviations: 4
- choice distribution: Both 198, None 34, Strategy 12, Case 6
- secondary query bootstrap CI: [-0.0067, 0.0440]

The point estimate is practically meaningful for this stage (+1.7pp), but the grouped CI crosses zero and deviation precision remains low.

## 8. Gain/Harm Selective Result

Best gain/harm variants:

| Feature set | Model | Accuracy | Gain vs Both | Coverage | Precision | Harm rate | Cluster 95% CI |
|---|---|---:|---:|---:|---:|---:|---:|
| synthetic interaction | logreg | 0.7560 | +0.0093 | 0.272 | 0.044 | 0.015 | [-0.0038, 0.0249] |
| existing_all + synthetic | logreg | 0.7547 | +0.0080 | 0.412 | 0.068 | 0.049 | [-0.0180, 0.0337] |

Gain/harm framing controls harm reasonably, but it deviates too often into neutral cases. It does not yet deliver high-precision exception routing.

## 9. Confidence Gating

Thresholds/lambdas were selected inside train folds only.

Observed behavior:

- best marginal regression coverage: 20.8%
- best gain/harm coverage: 27.2% to 41.2%
- harmful deviation rate is controlled, but many deviations are neutral rather than truly beneficial

The router behavior is closer to the desired default-Both policy than earlier four-arm classifiers, but still not selective enough. A useful router should likely have lower coverage and higher precision.

## 10. Grouped Statistical Evidence

Primary bootstrap: cluster percentile bootstrap by annual report, 10,000 resamples, seed 20260816.

Best result:

- point gain: +0.0173
- annual-report cluster 95% CI: [-0.0092, 0.0449]
- secondary query-level 95% CI: [-0.0067, 0.0440]

Conclusion: positive point estimate, but insufficient grouped statistical support.

## 11. Feature Ablation

Top annual-report grouped gains:

| Feature set | Best formulation | Gain |
|---|---|---:|
| existing_meta + compatibility | delta/ridge | +0.0173 |
| synthetic interaction | gain-harm/logreg | +0.0093 |
| existing_all + synthetic | gain-harm/logreg | +0.0080 |
| existing_meta + interaction | delta/rf | +0.0067 |
| existing_meta | delta/ridge | +0.0040 |
| synthetic scale | gain-harm/logreg | +0.0040 |

Compatibility features provide the clearest incremental signal. Scale-only features are weak in this setup. Full synthetic features do not monotonically improve results, likely because sparse positives make over-deviation easy.

## 12. Failure Analysis

What worked:

- The marginal-utility target is better aligned than four-arm correctness classification.
- Compatibility synthetic features improve the best annual grouped point estimate from +0.4pp to +1.7pp.
- Harmful deviation rate can be kept modest.

What failed:

- CI crosses zero under annual-report cluster bootstrap.
- Beneficial deviation support is tiny: only 24 queries have any deviation benefit, and only 6 have Case > Both.
- Deviation precision remains low because many selected deviations are neutral.
- Existing embeddings/retrieval metadata can correlate with some cases but do not provide strong enough observability.
- Synthetic features were generated after observing current failure modes, so they should be treated as exploratory.

Interpretation: stable heterogeneity exists, but current inference-time observable state is only weakly predictive for unseen annual reports.

## 13. Final Decision

**WEAK BUT PROMISING — IMPROVE OBSERVABILITY**

Do not proceed directly to full method development yet. The next step should improve observability of retrieved-content compatibility, especially:

- finer case/strategy operation alignment
- explicit operand-role matching
- scale convention and output-unit verification
- a stricter confidence gate that prefers abstaining to Both

The method direction remains valid: Both as default action + predict relative marginal utility of deviations. But current features are not yet strong enough for a robust selector claim.
