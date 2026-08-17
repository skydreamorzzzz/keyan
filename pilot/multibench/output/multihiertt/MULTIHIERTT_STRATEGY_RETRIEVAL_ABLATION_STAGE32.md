# MultiHiertt Strategy Retrieval Ablation — Stage 32

Date: 2026-08-17

## Scientific question

Does query representation richness (full context vs question-only) or candidate crowding
(multiple pool entries per family) better explain the family_top3=0.216 failure
from Stage 31?

## Setup

- Same frozen 32-strategy memory as Stage 31.
- Same 120-sample validation set (seed 20260817).
- Expanded top-k = 10 to enable family-deduplicated ranking.
- family_eligible_n = 111 / 120.
- Query variants: question_only (question text only) vs full_context (Stage 31 baseline).
- Ranking variants: raw_top3 (positions 1-3) vs dedup_top3 (family-deduplicated top-3 from top-10).

## 2×2 Summary (family top3, family-eligible samples)

| | raw_top3 | dedup_top3 | delta_dedup |
|---|---:|---:|---:|
| question_only | 0.532 | 0.658 | +0.126 |
| full_context | 0.216 | 0.216 | +0.000 |

- Delta query (question_only − full_context), raw: +0.315
- Delta query (question_only − full_context), dedup: +0.441
- Delta dedup (dedup − raw), full_context: +0.000
- Delta dedup (dedup − raw), question_only: +0.126

## All-sample type_top3

| | raw_top3 | dedup_top3 |
|---|---:|---:|
| question_only | 0.858 | 0.867 |
| full_context | 0.833 | 0.833 |

## Per-type breakdown: question_only raw_top3

| Type | N | Fam-elig | family_top3 | type_top3 |
|---|---:|---:|---:|---:|
| `program` | 100 | 93 | 0.560 | 1.000 |
| `span_comparison_lookup` | 6 | 6 | 0.000 | 0.000 |
| `span_comparison_yesno` | 2 | 0 | 0.000 | 0.000 |
| `span_computed_value_lookup` | 2 | 2 | 0.000 | 0.000 |
| `span_direct_lookup` | 3 | 3 | 0.333 | 0.333 |
| `span_superlative_lookup` | 7 | 7 | 0.286 | 0.286 |

## Per-type breakdown: full_context dedup_top3

| Type | N | Fam-elig | family_top3 | type_top3 |
|---|---:|---:|---:|---:|
| `program` | 100 | 93 | 0.200 | 0.960 |
| `span_comparison_lookup` | 6 | 6 | 0.500 | 0.500 |
| `span_comparison_yesno` | 2 | 0 | 0.000 | 0.000 |
| `span_computed_value_lookup` | 2 | 2 | 0.000 | 0.000 |
| `span_direct_lookup` | 3 | 3 | 0.333 | 0.333 |
| `span_superlative_lookup` | 7 | 7 | 0.000 | 0.000 |

## Crowding Diagnostic (full_context, raw_top3, program queries only)

- program_n: 100
- distinct families in top3: 1=1, 2=1, 3=98
- families dominating top1 in failing program queries: {'span:comparison_lookup': 31, 'program:difference': 17, 'span:direct_lookup': 10, 'program:division_composition': 8, 'program:projection_or_compound_change': 6}

## Decision

Best condition: `question_only__dedup_top3` with family_top3_eligible = 0.658.
Decision: `PROCEED_WITH_QUESTION_ONLY__DEDUP_TOP3_TO_STAGE33_HYDE`.
