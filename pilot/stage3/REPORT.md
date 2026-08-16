# Stage 3 Report: Selector Feasibility / Oracle-Gap Attribution

Date: 2026-08-16

Scope: official-aligned Stage 2 outputs only. No new LLM calls. Main analysis fixes Full-doc grounding and uses `prog` FinQA execution correctness. Structured grounding is reported only as robustness.

## 1. Artifacts

| Artifact | Purpose |
|---|---|
| `build_oracle_dataset.py` | Builds per-query oracle analysis records from Stage 2 official outputs plus current case/strategy retrieval. |
| `oracle_analysis_dataset.jsonl` / `.json` | 492 records. `features` are inference-time-safe; `labels` and `analysis` may contain correctness/gold-program-derived fields. |
| `oracle_gap_attribution.py` | Attribution statistics over oracle sets, interference, families, retrieval confidence, and consistency. |
| `oracle_gap_attribution.json` | Full-doc execution attribution. |
| `oracle_gap_attribution_structured.json` | Structured execution robustness attribution. |
| `run_selector_baselines.py` | 5-fold CV lightweight selectors using independent per-arm utility classifiers. |
| `selector_baselines.json` | Full-doc selector metrics. |
| `selector_baselines_structured.json` | Structured robustness selector metrics. |

Important separation:

- `features`: query-only and retrieval-conditioned signals available before choosing an arm.
- `labels`: arm correctness and oracle sets, used only as training/evaluation targets.
- `analysis`: gold-program-derived fields such as true operation family and step count, used only for attribution, not selector input.

## 2. Dataset Fields

Each record contains:

- sample index/id, filename, question
- safe query features: percent/ratio/change/aggregation/comparison flags, year/number counts, scale/unit words, inferred query family
- case retrieval: top-4 ids, scores, score margin, retrieved case family/struct/n_steps, top score statistics
- strategy retrieval: top-3 ids, scores, case-hit counts, strategy families, canonical scale text
- consistency/disagreement: case-strategy struct overlap, top-family agreement, score gap, confidence disagreement
- labels for Full-doc and Structured, both `prog` execution and official `ff` corrected-close
- oracle set per metric/grounding

Gold-program fields are present under `analysis` for attribution only. They are intentionally absent from selector feature matrices.

## 3. Oracle-Gap Attribution, Full-Doc Execution

The dataset exactly reproduces the Stage 2 official-aligned execution result:

| Arm | Accuracy |
|---|---:|
| None | 0.683 |
| Case | 0.720 |
| Strategy | 0.695 |
| Both | 0.728 |
| Best Fixed | 0.728 (`both`) |
| Oracle | 0.821 |
| Oracle Gap | +9.3pp |

Correct-arm set distribution:

| Pattern | Count |
|---|---:|
| all four correct | 278 |
| no arm correct | 88 |
| case + strategy + both | 28 |
| case + both | 17 |
| none only | 15 |
| none + case + both | 12 |
| strategy + both | 10 |
| none + strategy + both | 9 |
| none + strategy | 9 |
| case only | 7 |
| none + case | 7 |
| none + case + strategy | 4 |
| strategy only | 3 |
| none + both | 2 |
| both only | 2 |
| case + strategy | 1 |

Task-oriented complementarity counts:

| Contrast | Count |
|---|---:|
| Case correct, Strategy wrong | 43 |
| Strategy correct, Case wrong | 31 |
| Both wrong but Case or Strategy correct | 31 |

These are the same phenomena reported in Stage 2: the small exact-only numbers are stricter because they require all other arms wrong; the contrast counts are the useful utility-comparison view.

## 4. What Types Drive the Gap?

By gold problem family:

| Family | n | None | Case | Strategy | Both | Oracle |
|---|---:|---:|---:|---:|---:|---:|
| A comparison | 4 | 1.000 | 0.500 | 0.750 | 0.750 | 1.000 |
| B table aggregation | 20 | 0.900 | 0.850 | 0.850 | 0.850 | 0.950 |
| C unit scaling multi | 30 | 0.233 | 0.300 | 0.467 | 0.467 | 0.533 |
| E 3-step | 6 | 0.167 | 0.333 | 0.500 | 0.333 | 0.667 |
| F 2-step | 158 | 0.633 | 0.741 | 0.658 | 0.709 | 0.810 |
| G 1-step | 273 | 0.751 | 0.755 | 0.733 | 0.766 | 0.850 |

Main structure:

- Negative interference is concentrated in short ratio/change questions: 31 cases, mostly `F_2step` and `G_1step`; 22/31 are ratio-family and 6/31 change-family.
- Case beats Strategy on mostly short ratio/change tasks: 43 cases; `F_2step` 21, `G_1step` 21; case same-struct retrieval hit rate 72.1%.
- Strategy beats Case is also mostly short tasks but has more unit-scaling contribution: 31 cases; `G_1step` 15, `F_2step` 8, `C_unitscaling_multi` 5; case same-struct hit rate drops to 48.4%.
- Unit-scaling/multi-step remains the hardest high-value area: low fixed-arm accuracy but large oracle headroom.

## 5. Retrieval Signals

Retrieval confidence has signal, but it is not monotonic enough to be a router by itself.

Case top-score tertiles:

| Bin | n | Case Acc | None Acc | Case - None |
|---|---:|---:|---:|---:|
| low | 165 | 0.630 | 0.606 | +2.4pp |
| mid | 164 | 0.750 | 0.756 | -0.6pp |
| high | 163 | 0.779 | 0.687 | +9.2pp |

Strategy top-score tertiles:

| Bin | n | Strategy Acc | None Acc | Strategy - None |
|---|---:|---:|---:|---:|
| low | 165 | 0.691 | 0.715 | -2.4pp |
| mid | 164 | 0.695 | 0.695 | +0.0pp |
| high | 163 | 0.699 | 0.638 | +6.1pp |

Gold-family consistency is much stronger as an attribution signal:

| Condition | n | None | Case | Strategy | Both | Oracle |
|---|---:|---:|---:|---:|---:|---:|
| case retrieval has same gold struct | 361 | 0.753 | 0.825 | 0.781 | 0.820 | 0.886 |
| no same case struct | 131 | 0.489 | 0.427 | 0.458 | 0.473 | 0.641 |
| strategy retrieval matches gold struct | 383 | 0.742 | 0.812 | 0.783 | 0.817 | 0.883 |
| no strategy gold match | 109 | 0.477 | 0.394 | 0.385 | 0.413 | 0.606 |

This is useful evidence for predictable structure, but exact gold-family hit is not an inference-time feature. The router needs a non-gold proxy for this.

## 6. Selector Feasibility Baselines

Setup:

- 5-fold CV over the 492 records.
- Candidate arms: None / Case / Strategy / Both.
- Models: logistic regression, shallow decision tree, random forest, small MLP.
- Training target: per-arm correctness via independent binary utility classifiers.
- Selection: choose the arm with highest predicted utility probability.
- No gold answer, gold program, or arm correctness is used as input feature.

Full-doc execution results:

| Feature Set / Best Model | Accuracy | vs Best Fixed | Remaining Gap | Gap Recovery | Macro-F1 | Strategy>C Recall | Case>S Recall | Interference Avoid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Query-only / RF | 0.728 | +0.0pp | 9.3pp | 0.0% | 0.215 | 0.323 | 0.256 | 0.871 |
| Query + retrieval metadata / LogReg | 0.736 | +0.8pp | 8.5pp | 8.7% | 0.200 | 0.258 | 0.302 | 0.871 |
| Query + retrieved repr / LogReg | 0.734 | +0.6pp | 8.7pp | 6.5% | 0.213 | 0.355 | 0.419 | 0.903 |

The best Full-doc baseline is `query_retrieval_meta/logreg`:

- execution accuracy: 0.736
- improvement over best fixed: +0.8pp
- oracle gap recovery: 8.7%
- remaining gap: 8.5pp
- per-class recall against preferred oracle arm: None 0.291, Case 0.316, Strategy 0.500, Both 0.246

Structured robustness:

| Feature Set / Best Model | Accuracy | vs Best Fixed | Gap Recovery |
|---|---:|---:|---:|
| Query-only / LogReg | 0.661 | +0.4pp | 4.8% |
| Query + retrieval metadata / Tree | 0.669 | +1.2pp | 14.3% |
| Query + retrieved repr / LogReg | 0.671 | +1.4pp | 16.7% |

Structured shows the same direction, with slightly larger recovered gap, but still far from oracle.

## 7. Interpretation

Oracle gap is not random:

- gold operation/family and step complexity strongly stratify utility;
- retrieval family match separates high-utility from low-utility regions;
- Case-vs-Strategy wins have different retrieval consistency profiles;
- Both negative interference has a compact profile: mostly short ratio/change questions where adding both memories perturbs an otherwise solvable path.

However, current deployable proxies are weak:

- retrieval top score is only partially useful and not monotonic;
- the best Full-doc selector recovers only 8.7% of the oracle gap;
- macro-F1 against preferred oracle arm is around 0.20, meaning the selector is mostly exploiting broad utility tendencies, not reliably identifying the right arm;
- retrieved embedding snippets help some Case-vs-Strategy recall but do not improve Full-doc accuracy beyond retrieval metadata.

The framing is still valid: `U(m | q, r_m)` is the right object. The problem is feature quality, especially non-gold proxies for program family, retrieval semantic consistency, and conflict/scale-risk detection.

## 8. Known Caveats

- Gold-derived `analysis` fields are for attribution only. They must not be used as router input.
- Current retrieval metadata is dense-retrieval-centric. It does not inspect whether retrieved facts/numbers actually align with query operands.
- Stage 2 found Structured prompt scale pollution from Case `exe_ans` fractions. This report records scale/percent fields but does not rewrite memory representation.
- MLP baselines emitted convergence warnings; conclusions rely primarily on logistic regression, decision tree, and random forest.

## 9. Answers

1. **Oracle Gap 是否具有可预测结构？**

Yes. The gap is structured by operation family, step/scale complexity, retrieval family consistency, and case-strategy conflict. Gold-family consistency is especially predictive, but it is only an attribution signal unless replaced by an inference-time proxy.

2. **retrieval-conditioned features 是否明显优于 query-only？**

Modestly, not decisively. Full-doc query-only reaches best-fixed at 0.728; query + retrieval metadata reaches 0.736 (+0.8pp, 8.7% gap recovery). Structured robustness shows +1.4pp and 16.7% recovery with retrieved representations. Retrieval conditioning helps, but current features are not strong enough for a final router.

3. **是否值得进入下一轮正式 Adaptive Experience Utility Router 设计？**

Not as a final router yet. The selector framing is supported, but the next step should be better feature design: inference-time program-family prediction, retrieval semantic consistency, operand/unit alignment, and explicit scale-pollution risk signals.

Final decision: **NEED BETTER FEATURES**
