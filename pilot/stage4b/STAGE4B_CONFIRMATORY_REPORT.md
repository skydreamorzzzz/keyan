# Stage 4B: Conservative Router Freeze & Confirmatory Holdout

Date: 2026-08-16

## 1. Objective

Stage 4A found weak exploratory learnability under annual-report grouped CV:

- Always Both: about 74.67%
- Best exploratory selector: about 76.40%
- Gain: +1.73pp
- Annual-report cluster bootstrap CI crossed zero

That result was not confirmatory because feature set, formulation, and model were selected after comparing many outer-OOF results. Stage 4B tests whether the signal survives a stricter protocol and then freezes a router before touching fresh public-test holdout data.

## 2. Protocol Hardening

Implemented in `pilot/stage4b/`:

- `annual_report_group = COMPANY/YEAR` is the primary grouping unit.
- All preprocessing is fold-local. `DictVectorizer` is fit only on the current train fold, then applied to validation/test.
- Outer loop is `GroupKFold` by annual report and is used only for final OOF evaluation.
- Inner loop is grouped CV inside the outer-train split and selects feature set, formulation, model family, threshold, and lambda.
- Tie-breaking is conservative. Equal or statistically close validation utility prefers lower deviation coverage, higher threshold, higher harm penalty, and higher abstention.
- Runtime guard was added to `pilot/stage3/stability_run.py`: within a cache namespace, response model/fingerprint/runtime drift aborts the run instead of silently mixing runtimes.

Machine-readable outputs:

- `development_nested_results.json`
- `fixed_candidate_audit.json`
- `cost_analysis.json`
- `stage4b_frozen_router_config.json`
- `holdout_audit.json`
- `holdout_confirmation.json`

## 3. Fully Nested Development Result

Dataset: original 250-query runtime-normalized repeated subset, targets from `rn1/rn2/rn3`.

The fully nested conservative protocol selected zero OOF deviations:

| Policy | Expected accuracy | Gain vs Both | Oracle gap recovery | Deviation coverage |
|---|---:|---:|---:|---:|
| Always Both | 0.7467 | 0.0000 | 0.0% | 0.0% |
| Fully nested policy | 0.7467 | 0.0000 | 0.0% | 0.0% |
| Expected oracle | 0.8387 | +0.0920 | 100.0% | n/a |

Annual-report cluster bootstrap for policy minus Both:

- point estimate: 0.0000
- 95% CI: [0.0000, 0.0000]
- resamples: 10,000
- seed: 20260816

Interpretation: after removing winner's-curse model selection and applying conservative gating, the non-optimistic learned policy collapses to the default action `Both`.

## 4. Single-Execution Realized Stability

The frozen OOF action is fixed per query, then evaluated separately on each repeated execution replicate:

| Replicate | Policy accuracy | Both accuracy | Gain |
|---|---:|---:|---:|
| rn1 | 0.7480 | 0.7480 | 0.0000 |
| rn2 | 0.7440 | 0.7440 | 0.0000 |
| rn3 | 0.7480 | 0.7480 | 0.0000 |

Mean gain is 0.0, with range 0.0. Expected utility and single-execution realized utility agree because the frozen policy never deviates.

## 5. Hierarchical Router Audit

A small fixed candidate audit was run to separate the architecture question from post-hoc champion selection. These results are exploratory only and are not used to freeze the router.

| Candidate | Expected accuracy | Gain vs Both | Coverage | Beneficial / harmful deviations | Cluster 95% CI |
|---|---:|---:|---:|---:|---:|
| flat delta + compatibility | 0.7507 | +0.0040 | 2.4% | 2 / 1 | [-0.0055, 0.0161] |
| hierarchical + compatibility | 0.7360 | -0.0107 | 9.6% | 2 / 5 | [-0.0316, 0.0085] |
| hierarchical + synthetic interaction | 0.7560 | +0.0093 | 4.4% | 3 / 1 | [-0.0038, 0.0248] |
| gain/harm + synthetic interaction | 0.7467 | +0.0000 | 0.4% | 0 / 0 | [0.0000, 0.0000] |

The hierarchical formulation is not reliably superior. It can produce a small positive exploratory result with synthetic interaction features, but the CI crosses zero and realized per-replicate gain is 0.0 in the saved audit.

## 6. Accuracy-Memory Cost Pareto

Development expected utility and estimated prompt/memory tokens:

| Policy | Expected accuracy | Avg prompt tokens | Avg memory tokens |
|---|---:|---:|---:|
| Always None | 0.6933 | 685.0 | 0.0 |
| Always Strategy | 0.7053 | 894.3 | 209.3 |
| Always Case | 0.7160 | 1098.3 | 413.3 |
| Always Both | 0.7467 | 1307.6 | 622.6 |
| Frozen router | 0.7467 | 1307.6 | 622.6 |

The frozen router is exactly Always Both, so it does not create a better accuracy-memory tradeoff on development data. Stage 4A's neutral/beneficial low-coverage deviations remain exploratory.

## 7. Frozen Router

Frozen config: `stage4b_frozen_router_config.json`

Frozen spec: `FROZEN_ROUTER_SPEC.md`

The frozen router is:

```text
for every query:
    choose Both
```

This is a deliberate conservative freeze. It prevents using holdout results to re-enable an exploratory Stage 4A candidate. The confirmatory holdout therefore tests whether any non-optimistic accuracy or memory-cost benefit remains after protocol hardening.

## 8. Holdout Definition

Holdout source: `data/finqa/test.json`.

Primary holdout rule was frozen before execution:

```text
public test samples whose annual_report_group is disjoint from both train.json and dev[:492]
```

Audit:

- public test size: 1,147
- public test annual reports: 278
- train annual reports: 741
- dev[:492] annual reports: 208
- primary report-disjoint holdout: 97 queries
- primary report-disjoint annual reports: 33

The public private-test file does not contain executable gold labels, so it is not used for confirmatory execution accuracy.

## 9. Confirmatory Holdout Execution

The frozen router never deviates, so only the Both baseline needed execution. Two independent confirmatory replicates were run on the 97-query report-disjoint holdout.

Runtime provenance in both caches:

- provider: DeepSeek
- backend: official OpenAI-compatible API
- requested/effective/response model: `deepseek-v4-flash`
- thinking mode: false
- temperature: 0
- max tokens: 600
- system fingerprint: `a26a7955944dc5c60445bff77fac9c8e`
- endpoint: `https://api.deepseek.com/chat/completions`

Execution results:

| Replicate | Both accuracy | Frozen router accuracy | Gain | Coverage | Cluster 95% CI |
|---|---:|---:|---:|---:|---:|
| h1 | 0.7526 | 0.7526 | 0.0000 | 0.0% | [0.0000, 0.0000] |
| h2 | 0.7629 | 0.7629 | 0.0000 | 0.0% | [0.0000, 0.0000] |

API usage:

- execution calls: 194 Both calls
- selected deviation calls: 0
- holdout synthetic feature calls: 0

Holdout token estimates:

| Prompt/action | Avg prompt tokens | Avg memory tokens |
|---|---:|---:|
| None | 663.8 | 0.0 |
| Strategy | 867.2 | 203.4 |
| Case | 1071.8 | 408.0 |
| Both | 1275.2 | 611.4 |
| Frozen router | 1275.2 | 611.4 |

Confirmatory conclusion: the frozen router preserves Both accuracy but provides no accuracy gain and no memory-cost reduction.

## 10. Exploratory vs Confirmatory Evidence

Exploratory evidence:

- Stage 4A best OOF result: +1.73pp, CI crossed zero.
- Fixed Stage 4B candidate audit: hierarchical + synthetic interaction reached +0.93pp expected gain at 4.4% coverage, CI crossed zero.

Confirmatory evidence:

- Fully nested development policy: +0.00pp, zero deviations.
- Fresh report-disjoint holdout: +0.00pp in both replicates, zero deviations.
- No memory-token savings from the frozen router.

The current inference-time features do not support a conservative deployable router. The repeated-history ceiling remains real, but the available observable state is not enough to produce a confirmatory unseen-query deviation policy under this protocol.

## 11. Final Decision

**DEVELOPMENT SIGNAL DID NOT REPLICATE**

Stage 4B does not falsify stable marginal-utility heterogeneity itself. It does falsify the stronger claim that the current Stage 4A feature/model search already yields a conservative, confirmable unseen-query router.

Next work should not keep tuning thresholds on the same 250-query subset. A better next step is to improve observability before another confirmatory attempt: retrieved-content reasoning, operand-role verification, scale/unit consistency checks, and explicit memory conflict modeling, with a pre-registered router freeze before any new holdout execution.
