# Stage 4B.2: Router Stability & Accuracy-Memory Pareto Audit

Date: 2026-08-16

## Scope

This audit changes only the one-standard-error calculation from population standard deviation to sample standard deviation:

```text
SE = std(vals, ddof=1) / sqrt(n)
```

No API calls were made. No features, architectures, models, thresholds, lambdas, runtime, retrieval, memory, or evaluator settings were changed.

## 1. Sample-SE Sensitivity

Stage 4B.1 used paired gain and explicit Always Both, but its SE helper still used population std. Stage 4B.2 reruns the same nested OOF procedure with sample std.

| Metric | Stage 4B.1 population-SE | Stage 4B.2 sample-SE |
|---|---:|---:|
| Always Both | 0.7467 | 0.7467 |
| Nested OOF policy | 0.7520 | 0.7440 |
| Gain vs Both | +0.0053 | -0.0027 |
| Deviation coverage | 5.6% | 5.2% |
| Beneficial deviations | 2 | 0 |
| Harmful deviations | 1 | 1 |
| Neutral deviations | 11 | 12 |
| Cluster 95% CI | [-0.0054, 0.0192] | [-0.0084, 0.0000] |

Corrected realized gains under sample-SE:

| Replicate | Policy accuracy | Both accuracy | Gain |
|---|---:|---:|---:|
| rn1 | 0.7480 | 0.7480 | +0.0000 |
| rn2 | 0.7400 | 0.7440 | -0.0040 |
| rn3 | 0.7440 | 0.7480 | -0.0040 |

The Stage 4B.1 positive signal is not robust to the more conservative sample-SE estimate.

## 2. Router Stability

Outer-fold selected architectures:

| Architecture | Count |
|---|---:|
| flat_delta | 2 |
| gain_harm | 2 |
| always_both | 1 |

Outer-fold selected feature sets:

| Feature set | Count |
|---|---:|
| synthetic_interaction | 4 |
| none | 1 |

Thresholds:

| Threshold | Count |
|---|---:|
| 0.05 | 1 |
| 0.2 | 1 |
| 0.5 | 2 |
| None | 1 |

Inner selected coverages:

```text
[0.1661, 0.0000, 0.0200, 0.0598, 0.0150]
```

Average inner selected coverage: 5.2%.

The procedure is unstable at the model-selection level: folds disagree across architecture, threshold, and whether to abstain entirely. Therefore the nested OOF number should be interpreted as the performance of a model-selection procedure, not a single deployable router.

## 3. OOF Accuracy-Memory Pareto

Expected utility and prompt/memory token estimates:

| Policy | Expected accuracy | Avg prompt tokens | Avg memory tokens |
|---|---:|---:|---:|
| Always None | 0.6933 | 685.0 | 0.0 |
| Always Strategy | 0.7053 | 894.3 | 209.3 |
| Always Case | 0.7160 | 1098.3 | 413.3 |
| Always Both | 0.7467 | 1307.6 | 622.6 |
| Sample-SE nested OOF policy | 0.7440 | 1286.2 | 601.3 |

Relative to Always Both:

- accuracy: -0.27pp
- avg prompt tokens: -21.4
- avg memory tokens: -21.4

This is not a clear Pareto improvement. It slightly reduces memory/context but loses expected accuracy.

## 4. Deviation Efficiency

Sample-SE nested OOF deviations:

| Bucket | Count | Actions | Avg prompt-token saving vs Both | Avg memory-token saving vs Both |
|---|---:|---|---:|---:|
| Beneficial | 0 | {} | 0.0 | 0.0 |
| Neutral | 12 | None: 6, Case: 6 | 409.3 | 409.3 |
| Harmful | 1 | Strategy: 1 | 427.0 | 427.0 |

Neutral deviations do save substantial tokens when they happen. However, because coverage is only 5.2%, the total average saving is small. The single harmful deviation also saves tokens, so token saving alone is not a sufficient correctness-preserving signal.

Conclusion: neutral deviations hint at an efficiency direction, but this run does not establish a clear accuracy-memory Pareto gain.

## 5. Deployable Candidate Freeze

Using the same conservative inner-CV procedure on all 250 development samples selected:

```json
{
  "architecture": "flat_delta",
  "feature_set": "existing_meta_plus_interaction",
  "threshold": 0.5,
  "lambda": null,
  "mean_utility": 0.7482947663670555,
  "se_utility": 0.03980903852328979,
  "mean_gain": 0.0013705616115254893,
  "se_gain": 0.005809644135436938,
  "coverage": 0.031889462612354175
}
```

Artifacts:

- `stage4b2_deployable_candidate_config.json`
- `STAGE4B2_DEPLOYABLE_CANDIDATE_SPEC.md`

This is a candidate freeze only. Its development selection statistics are not confirmatory evidence. A fresh holdout would be required before making method claims.

The old Stage 4B Always Both freeze is marked as superseded in `stage4b_frozen_router_config.json`.

## 6. Interpretation

Stage 4B.1 showed that the original collapse-to-Both was partly a protocol artifact. Stage 4B.2 shows that the repaired positive signal is fragile: a standard sample-SE correction changes the fully nested OOF policy from weakly positive to weakly negative.

The accuracy-memory story is also not strong enough:

- OOF accuracy falls below Both.
- Average token savings are small at the policy level.
- Neutral deviations save tokens locally, but their coverage is too low to establish a clear Pareto frontier point.
- Outer-fold model selection is unstable.

## Final Judgment

**SIGNAL DISAPPEARS UNDER SAMPLE-SE**

The current Stage 4B feature/model/protocol stack should not be treated as a reliable router. The next useful step is not more tuning on the same 250 queries; it is either a pre-registered efficiency objective with stronger safety constraints or better observable features for retrieved-content compatibility.
