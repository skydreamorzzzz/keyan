# MultiHiertt Strategy Retrieval Audit

Date: 2026-08-17

Scope: retrieval-only audit for frozen `multihiertt_strategy_memory_v0.json` (32 strategies). No LLM/API calls, no strategy edits, no family changes, no four-arm execution, no router.

## Setup

- Strategy memory: 32 frozen strategies (12 coarse-level + 20 schema-level).
- Retriever: `BAAI/bge-small-en-v1.5` on `cpu`.
- Top-k: 3.
- Fixed validation sample: 120 examples, seed `20260817` (same seed as Case Memory audit, ensures consistency).
- Target query text uses only inference-visible fields: question, paragraphs, hierarchical HTML table previews, table descriptions via `multihiertt_case_memory.make_target_retrieval_text()`.
- Gold family/type/schema/evidence/scale/multi_table used only after retrieval for post-hoc diagnostics.

## Pool Coverage

- Gold family present in frozen pool (12 coarse families): 111 / 120 (0.925).
- Gold fine schema_key present in schema-level pool (20 schemas): 53 / 120 (0.442).
- Primary eligibility gate is family-level (coarse pool covers top families). Exact schema eligibility is lower by design (top-20 covers ~50% of train schema distribution).

## Retrieval Ablation: All Samples

| Variant | Family top1 | Family top3 | Type top1 | Type top3 | Exact schema top3 | Evidence top3 | Scale top3 | Multi-table top3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Semantic-rich | 0.042 | 0.200 | 0.450 | 0.833 | 0.017 | 0.825 | 0.733 | 0.850 |
| Schema-only | 0.192 | 0.300 | 0.833 | 0.833 | 0.108 | 0.875 | 0.833 | 0.950 |

## Retrieval Ablation: Family-Eligible Only

| Variant | Family top1 | Family top3 | Type top3 | Exact schema top3 | Evidence top3 | Scale top3 |
|---|---:|---:|---:|---:|---:|---:|
| Semantic-rich | 0.045 | 0.216 | 0.847 | 0.018 | 0.829 | 0.730 |
| Schema-only | 0.207 | 0.324 | 0.838 | 0.117 | 0.883 | 0.838 |

## Retrieval Ablation: Schema-Eligible Only

| Variant | Family top3 | Type top3 | Exact schema top1 | Exact schema top3 | Evidence top3 | Scale top3 |
|---|---:|---:|---:|---:|---:|---:|
| Semantic-rich | 0.208 | 0.830 | 0.000 | 0.038 | 0.849 | 0.811 |
| Schema-only | 0.415 | 0.774 | 0.094 | 0.245 | 0.887 | 0.906 |

Semantic minus schema-only family top3 (family-eligible): -0.108.
Semantic minus schema-only type top3 (all samples): +0.000.

## By Strategy Type

| Type | N | Fam-elig | Sch-elig | Sem family top3 | Sch-only family top3 | Sem type top3 | Sch-only type top3 | Sem exact schema top3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `program` | 100 | 93 | 41 | 0.200 | 0.360 | 0.960 | 1.000 | 0.020 |
| `span_comparison_lookup` | 6 | 6 | 5 | 0.500 | 0.000 | 0.500 | 0.000 | 0.000 |
| `span_comparison_yesno` | 2 | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| `span_computed_value_lookup` | 2 | 2 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| `span_direct_lookup` | 3 | 3 | 0 | 0.333 | 0.000 | 0.333 | 0.000 | 0.000 |
| `span_superlative_lookup` | 7 | 7 | 7 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

## Typical Correct Retrievals

- `multihiertt:validation:f5b5bb74596148978c9f5ea7efb1a149`: gold `program:division_composition`; top3 families `['program:ratio', 'span:comparison_lookup', 'program:division_composition']`; question: what portion of the compensation expense in 2017 is relates to the acceleration of equity awards upon termination of employment at baker hughes?
- `multihiertt:validation:0565d8b781a14a29852db42ceaf3644e`: gold `program:division_composition`; top3 families `['program:projection_or_compound_change', 'program:difference', 'program:division_composition']`; question: what is the money pool activity use of operating cash flows as a percentage of receivables from the money pool in 2003?
- `multihiertt:validation:27ca5c5366c941c5841fd2b54be97835`: gold `program:change_rate`; top3 families `['program:ratio', 'program:division_composition', 'program:change_rate']`; question: by what percentage did total residential mortgages increase from 2011 to 2012?
- `multihiertt:validation:1c1d7c56d70842a48980735e10a853ae`: gold `program:ratio`; top3 families `['program:division_composition', 'program:ratio', 'program:average_or_composed_division']`; question: What is the ratio of Distribution fees to the total in 2012?
- `multihiertt:validation:859ddaa4993048b1978ff5b0b6bf0a92`: gold `program:aggregation_sum`; top3 families `['span:comparison_lookup', 'program:aggregation_sum', 'program:ratio']`; question: for december 31 , 2009 , what was the total value of segregated collateral for the benefit of brokerage customers in millions?

## Typical Errors

- `multihiertt:validation:6e69e996da0a482b87e237352da9369b`: gold `program:difference`; top1 `program:aggregation_sum`; top3 families `['program:aggregation_sum', 'program:aggregation_sum', 'program:aggregation_sum']`; question: What is the sum of Investment real estate in 2012 and Gain (loss) recognized in OCI on derivatives in 2011? (in million)
- `multihiertt:validation:c649cb8dafee4d23b4184b0c8c89e74f`: gold `program:change_rate`; top1 `program:projection_or_compound_change`; top3 families `['program:projection_or_compound_change', 'program:difference', 'program:ratio']`; question: In the year with the most Interest cost in Table 1, what is the growth rate of Environmental in Table 0?
- `multihiertt:validation:faac106d01bb414e8459e88d762e51b4`: gold `span:superlative_lookup`; top1 `span:comparison_lookup`; top3 families `['span:comparison_lookup', 'span:direct_lookup', 'program:difference']`; question: What's the greatest value of Stores Opened in 2011?
- `multihiertt:validation:776342a2d8c1492286eedc213289f373`: gold `program:change_rate`; top1 `span:comparison_lookup`; top3 families `['span:comparison_lookup', 'span:direct_lookup', 'program:difference']`; question: In the year with the most Granted for shares(in thousands), what is the growth rate of Outstanding ? (in %)
- `multihiertt:validation:627ffb2c46b94bdcb58d0850493a36ea`: gold `program:average_or_composed_division`; top1 `program:difference`; top3 families `['program:difference', 'span:comparison_lookup', 'span:direct_lookup']`; question: What's the average of Capital leases of Carrying amount in 2003 and 2002? (in Thousand)

## Interpretation

Semantic abstraction hurts family retrieval alignment compared to schema-only metadata by -0.108 family top3 on family-eligible samples.

Main failure modes:

- Dense retrieval may overweight surface semantic cues and miss structural schema distinctions (evidence modality, table count, scale hint).
- Coarse strategies for the same answer type (all program families) are semantically similar, making fine-grained disambiguation challenging without query reformulation.
- Multi-table evidence queries may retrieve single-table strategies when the question wording does not explicitly reference multiple tables.
- Span strategy types (superlative, comparison) may be confused by program-like arithmetic language in MultiHiertt questions.
- The frozen v0 pool covers only top families, so some dev samples' families are out-of-pool.

## Decision

Decision: `NEEDS RETRIEVAL REVISION BEFORE FOUR-ARM DRY-RUN`.

Primary metric: semantic-rich family top3 on family-eligible samples = 0.216.
Type top3 all samples = 0.833.
Exact schema top3 on schema-eligible samples = 0.038.
