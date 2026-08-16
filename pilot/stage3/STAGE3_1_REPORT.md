# Stage 3.1 Report: Inference-Time Retrieval Utility Features

Date: 2026-08-16

Scope: continue from `pilot/stage3/`. No Stage 2 arm outputs were regenerated. No new LLM calls. Main experiment remains Full-doc grounding with `prog` execution correctness; Structured is robustness only.

## 1. Audit of Existing Stage 3 Features

Existing Stage 3 feature groups:

- Query-only flags: keyword booleans for percent/ratio/change/average/sum/compare/max-min, year/number counts, unit/scale words.
- Retrieval metadata: top score, second score, mean/std, score margin, top case n_steps, family entropy, case-strategy score gap, struct overlap.
- Retrieved representation: first 64 dimensions of mean case/strategy embedding.
- Existing family metadata: retrieved Case `operation_family` from historical program structure and Strategy `program_family`, compared only to rough query keyword family.

Why they were insufficient:

- Cosine/top score captures topical similarity but not whether the retrieved memory uses the same calculation template.
- Margin and entropy say whether retrieval is confident, but not whether the confident result is structurally correct.
- Query flags are coarse and often confound ratio, average, percent-change, and unit-scaling questions.
- Retrieved embedding dimensions are hard to interpret and did not improve Full-doc accuracy over metadata.
- The strongest attribution signal from Stage 3 was gold-family consistency, but exact same-struct/gold-family hit is not deployable.

## 2. New Artifacts

| Artifact | Purpose |
|---|---|
| `build_alignment_features.py` | Builds Stage 3.1 inference-time-safe structural, operand, unit/scale, and semantic consistency features. |
| `alignment_feature_dataset.jsonl` / `.json` | Enriched 492-record dataset with `features_stage3_1` and `stage3_1` metadata. |
| `alignment_feature_quality.json` | Offline proxy quality against gold-family consistency. |
| `run_stage3_1_selectors.py` | Feature ablation selectors over previous and new feature groups. |
| `selector_stage3_1_full_doc.json` | Full-doc ablation results. |
| `selector_stage3_1_structured.json` | Structured robustness ablation results. |
| `analyze_stage3_1.py` | Alignment bucket utility analysis. |
| `stage3_1_alignment_analysis.json` | Full-doc utility by high/mid/low alignment buckets. |
| `stage3_1_alignment_analysis_structured.json` | Structured robustness bucket analysis. |

All new selector inputs are inference-time safe. Gold fields are used only for offline diagnostics in `alignment_feature_quality.json` and reports.

## 3. New Feature Design

### 3.1 Predicted Reasoning Family

Rule-based query parser predicts:

- `ratio`
- `percentage_change`
- `difference`
- `comparison`
- `aggregation`
- `average`
- `unit_scaling`
- `multiplication`
- `multi_step`
- `other`

Then it constructs:

- predicted-query-family one-hots
- Case top-k family agreement
- Strategy family agreement
- top-k agreement ratio
- Case/Strategy predicted-family disagreement

The parser uses only current query text and retrieved memory metadata/content. It does not use current gold program.

### 3.2 Operand / Structure Alignment

The builder extracts coarse roles from query and retrieved memory text:

- numerator / denominator
- part / whole
- old_value / new_value
- quantity / monetary_metric / share_metric
- sum_components / count
- scaling_factor
- percent_target / fraction_target
- comparison sides

It then creates:

- role-overlap scores
- year-count compatibility
- comparison/ratio/change symbolic compatibility
- top Case n_steps distance proxy
- Case/Strategy struct mode share
- Case/Strategy structure entropy
- top1 conflict-with-rest indicators

Historical Case program structure is allowed because it is part of memory content. Current query gold program is not used.

### 3.3 Unit / Scale Compatibility

New scale-risk features include:

- query asks/outputs percent
- query has raw scale words: thousand/million/billion/basis points
- retrieved Case output/profile indicates percent/fraction/raw number
- Strategy canonical scale convention
- Case/query scale mismatch
- Strategy/query scale mismatch
- Case/Strategy scale disagreement
- percent-query with fraction-memory pollution risk

This records the Stage 2 scale-pollution issue as features only; memory representation was not rewritten.

### 3.4 Retrieval Semantic Consistency

New consistency features include:

- top-k Case family consistency
- top-k Case program-structure consistency
- Case retrieval structure entropy
- Strategy top-k agreement
- Case/Strategy family and scale disagreement
- retrieval score multiplied by structural/role agreement
- top1-vs-rest conflict indicators
- high/low alignment buckets

Goal: separate “embedding similar but reasoning not aligned” from “embedding similar and structurally aligned”.

## 4. Proxy Quality Against Gold-Family Consistency

Predicted query family vs gold operation family:

| Metric | Value |
|---|---:|
| Exact accuracy | 0.311 |
| Compatible accuracy | 0.427 |

Predicted-family agreement as a deployable proxy for gold same-struct/family retrieval hit:

| Proxy | Precision | Recall | Accuracy |
|---|---:|---:|---:|
| Case predicted-family agreement -> Case gold same-struct hit | 0.768 | 0.817 | 0.685 |
| Strategy predicted-family agreement -> Strategy gold family hit | 0.804 | 0.846 | 0.720 |

Interpretation:

- The proxy catches many true family-consistent retrievals.
- It has substantial false positives: family-level agreement is too broad to prove operand/template correctness.
- It is useful as a weak retrieval-quality signal, not a substitute for gold-family consistency.

## 5. Utility by Alignment Bucket

Full-doc execution:

| Alignment bucket | n | None | Case | Strategy | Both | Oracle |
|---|---:|---:|---:|---:|---:|---:|
| high | 269 | 0.740 | 0.796 | 0.784 | 0.777 | 0.859 |
| mid | 184 | 0.614 | 0.630 | 0.592 | 0.679 | 0.766 |
| low | 39 | 0.615 | 0.615 | 0.564 | 0.615 | 0.821 |

Structured robustness:

| Alignment bucket | n | None | Case | Strategy | Both | Oracle |
|---|---:|---:|---:|---:|---:|---:|
| high | 269 | 0.684 | 0.706 | 0.662 | 0.699 | 0.777 |
| mid | 184 | 0.554 | 0.598 | 0.630 | 0.620 | 0.701 |
| low | 39 | 0.564 | 0.462 | 0.436 | 0.538 | 0.692 |

The high bucket is meaningfully easier and memory utility is generally higher. The low bucket identifies some harmful memory regions, especially Strategy. But the buckets also track overall question solvability: high alignment raises None accuracy too. This weakens direct arm selection.

## 6. Selector Ablation Results

Models: logistic regression, shallow decision tree, random forest, small MLP. Same 5-fold CV and per-arm binary utility formulation as Stage 3.

### 6.1 Full-doc Main Result

Best Stage 3 baseline remains unchanged:

| Feature group / model | Accuracy | vs Best Fixed | Gap Recovery | Macro-F1 | Case>Strategy recall | Strategy>Case recall | Negative interference avoid |
|---|---:|---:|---:|---:|---:|---:|---:|
| previous retrieval metadata / LogReg | 0.736 | +0.8pp | 8.7% | 0.200 | 0.302 | 0.258 | 0.871 |
| predicted family / MLP | 0.736 | +0.8pp | 8.7% | 0.191 | 0.442 | 0.226 | 0.839 |
| previous + all Stage 3.1 / MLP | 0.734 | +0.6pp | 6.5% | 0.185 | 0.326 | 0.258 | 0.774 |
| all Stage 3.1 / MLP | 0.732 | +0.4pp | 4.3% | 0.201 | 0.372 | 0.323 | 0.806 |
| operand/structure / MLP | 0.730 | +0.2pp | 2.2% | 0.200 | 0.535 | 0.258 | 0.774 |

Notable tradeoff:

- Operand/structure features improve Case>Strategy recall to 0.535, but reduce overall accuracy.
- Unit/scale features improve Strategy>Case recall in some models, but are too sparse/noisy and do not improve accuracy.
- All Stage 3.1 features do not add stable predictive value beyond previous retrieval metadata.

### 6.2 Structured Robustness

| Feature group / model | Accuracy | vs Best Fixed | Gap Recovery | Macro-F1 | Case>Strategy recall | Strategy>Case recall | Negative interference avoid |
|---|---:|---:|---:|---:|---:|---:|---:|
| all Stage 3.1 / MLP | 0.673 | +1.6pp | 19.0% | 0.211 | 0.233 | 0.435 | 0.793 |
| previous retrieval metadata / Tree | 0.669 | +1.2pp | 14.3% | 0.184 | 0.300 | 0.348 | 0.897 |
| previous + all Stage 3.1 / MLP | 0.667 | +1.0pp | 11.9% | 0.192 | 0.233 | 0.174 | 0.690 |
| predicted family / MLP | 0.663 | +0.6pp | 7.1% | 0.212 | 0.433 | 0.217 | 0.655 |

Structured gains are slightly better than Stage 3, but the best improvement over previous Structured best is only about +0.2pp (`0.671` -> `0.673`) and comes from MLP with convergence warnings. This is not strong enough evidence for a robust router feature set.

## 7. Why the New Features Did Not Lift Full-doc Selection

1. Predicted family is too coarse.

It has decent recall as a proxy for retrieval family consistency, but exact query-family accuracy is low. Ratio, average, percentage-change, difference, and unit-scaling are often collapsed or confused by keyword rules.

2. Family agreement is not operand agreement.

Many false positives are structurally plausible but operand roles differ. For example, a retrieved divide program may be part/whole, per-unit average, margin, or conversion. They all look compatible at family level but can push different reasoning.

3. Alignment tracks general solvability.

High alignment buckets improve Case/Strategy utility, but also improve None. A selector needs arm-specific marginal utility, not just “this query is easier and retrieval is coherent.”

4. Scale-risk features are sparse in Full-doc execution.

The Stage 2 percent/fraction pollution is real, especially for structured corrected-close behavior, but Full-doc `prog` execution labels do not expose enough failures for these features to drive selection.

5. Current formulation may penalize useful abstention.

The independent per-arm binary classifiers produce similar probabilities for correlated arms. Many queries have all four arms correct, while the valuable distinctions live in small Case>Strategy / Strategy>Case / interference subsets. Lightweight classifiers mostly learn broad correctness, not marginal utility.

## 8. Answers

1. **predicted structural alignment 能否替代 gold-family consistency 的一部分信息？**

Partially. Case proxy precision/recall is 0.768/0.817, and Strategy proxy precision/recall is 0.804/0.846 against offline gold-family consistency. It is a usable weak proxy, but false positives are too common because family agreement does not verify operand/template alignment.

2. **operand / scale / consistency features 是否提升 utility prediction？**

Not reliably for Full-doc. They improve some targeted recalls, especially Case>Strategy recall for operand/structure features, but they do not beat the previous `query + retrieval metadata` selector. Structured robustness shows a tiny improvement, but it is not stable enough to claim a real feature breakthrough.

3. **当前 feature 是否已经足够进入正式 Router 设计？**

No. The selector framing is still plausible, but current rule-based features are not enough. The next step should reason over retrieved content more directly: match query operands to retrieved case facts/program roles, check numerical/unit bindings, and identify when a retrieved strategy’s template actually fits the query.

Final decision: **NEED RETRIEVED-CONTENT REASONING**
