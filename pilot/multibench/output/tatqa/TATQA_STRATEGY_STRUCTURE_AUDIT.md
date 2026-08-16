# TAT-QA Strategy Structure Audit

Date: 2026-08-16

Scope: deterministic offline structure audit over TAT-QA train only. No LLM/API calls, no Strategy Memory construction, no four-arm experiment, no router.

## Train Distribution

- Train samples: 13215.
- Answer type: `{'multi-span': 1645, 'span': 5722, 'arithmetic': 5543, 'count': 305}`.
- Answer source: `{'table': 5920, 'text': 3125, 'table-text': 4170}`.
- Scale: `{'none': 6457, 'percent': 2104, 'thousand': 2481, 'million': 2153, 'billion': 20}`.
- Derivation present: 6603 (0.500).

| Answer type | Count | Derivation present | Coverage |
|---|---:|---:|---:|
| `span` | 5722 | 679 | 0.119 |
| `arithmetic` | 5543 | 5543 | 1.000 |
| `multi-span` | 1645 | 76 | 0.046 |
| `count` | 305 | 305 | 1.000 |

Top joint combinations of answer type, derivation presence, operator sequence, answer source, and scale:

| Answer type | Derivation | Operator sequence | Source | Scale | Count | Rate |
|---|---|---|---|---|---:|---:|
| `span` | `no_derivation` | `none` | `text` | `none` | 2704 | 0.205 |
| `arithmetic` | `derivation` | `subtract>divide` | `table` | `percent` | 912 | 0.069 |
| `span` | `no_derivation` | `none` | `table-text` | `thousand` | 574 | 0.043 |
| `multi-span` | `no_derivation` | `none` | `table-text` | `none` | 558 | 0.042 |
| `span` | `derivation` | `none` | `table` | `none` | 541 | 0.041 |
| `arithmetic` | `derivation` | `subtract` | `table` | `million` | 516 | 0.039 |
| `arithmetic` | `derivation` | `subtract` | `table-text` | `thousand` | 486 | 0.037 |
| `span` | `no_derivation` | `none` | `table-text` | `none` | 403 | 0.030 |
| `span` | `no_derivation` | `none` | `table` | `none` | 383 | 0.029 |
| `multi-span` | `no_derivation` | `none` | `table` | `none` | 369 | 0.028 |
| `span` | `no_derivation` | `none` | `table-text` | `million` | 358 | 0.027 |
| `arithmetic` | `derivation` | `subtract` | `table` | `thousand` | 344 | 0.026 |
| `arithmetic` | `derivation` | `subtract>divide` | `table-text` | `percent` | 332 | 0.025 |
| `arithmetic` | `derivation` | `subtract` | `table-text` | `million` | 315 | 0.024 |
| `arithmetic` | `derivation` | `divide` | `table` | `percent` | 313 | 0.024 |
| `span` | `no_derivation` | `none` | `table` | `million` | 290 | 0.022 |
| `arithmetic` | `derivation` | `subtract` | `table` | `none` | 273 | 0.021 |
| `arithmetic` | `derivation` | `add>divide` | `table` | `million` | 235 | 0.018 |
| `span` | `no_derivation` | `none` | `table` | `thousand` | 219 | 0.017 |
| `multi-span` | `no_derivation` | `none` | `table-text` | `thousand` | 218 | 0.016 |

## Operator Sequence Coverage

| Operator sequence | Count | Rate |
|---|---:|---:|
| `none` | 7672 | 0.581 |
| `subtract` | 2151 | 0.163 |
| `subtract>divide` | 1278 | 0.097 |
| `add>divide` | 768 | 0.058 |
| `divide` | 519 | 0.039 |
| `add` | 221 | 0.017 |
| `add>add>divide` | 220 | 0.017 |
| `divide>subtract` | 83 | 0.006 |
| `add>add` | 76 | 0.006 |
| `multiply` | 29 | 0.002 |
| `add>add>add>add>divide` | 21 | 0.002 |
| `add>divide>subtract>add>divide` | 17 | 0.001 |
| `add>add>add>divide` | 17 | 0.001 |
| `add>add>add` | 11 | 0.001 |
| `add>add>divide>subtract>add` | 10 | 0.001 |

## Deterministic Arithmetic Normalization

Arithmetic derivations are treated as TAT-QA formula strings, not FinQA programs. The normalization:

- replaces concrete numeric literals, years, percentages, and currency-marked numbers with ordered operand placeholders `O1`, `O2`, ...;
- removes specific units into `UNIT` markers when they appear inside the formula;
- preserves only arithmetic operators, parentheses, operand count, operation order, and coarse composed family;
- does not attempt to recover table cell references or convert formulas into the FinQA DSL.

Examples:

| Raw derivation | Normalized | Operators | Family | Scale |
|---|---|---|---|---|
| `(2.9+2.9)/2` | `( O1 + O2 ) / O3` | `add>divide` | `arithmetic:division_composition` | `percent` |
| `(2.7+2.7)/2` | `( O1 + O2 ) / O3` | `add>divide` | `arithmetic:division_composition` | `percent` |
| `[(2.9+2.9)/2] - [(2.7+2.7)/2]` | `( ( O1 + O2 ) / O3 ) - ( ( O4 + O5 ) / O6 )` | `add>divide>subtract>add>divide` | `arithmetic:change_or_composed_ratio` | `percent` |
| `(16,284 - 6,509) / 6,509 ` | `( O1 - O2 ) / O3` | `subtract>divide` | `arithmetic:percent_change` | `percent` |
| `12,907 - 8,538 ` | `O1 - O2` | `subtract` | `arithmetic:difference` | `thousand` |
| ` 11,459 - 11,486 ` | `O1 - O2` | `subtract` | `arithmetic:difference` | `thousand` |
| `(1,617-1,434)/1,434` | `( O1 - O2 ) / O3` | `subtract>divide` | `arithmetic:percent_change` | `percent` |
| `(18.1+15.1+14.4) / 3` | `( O1 + O2 + O3 ) / O4` | `add>add>divide` | `arithmetic:division_composition` | `percent` |
| `(14.8+14.7+14.6) / 3` | `( O1 + O2 + O3 ) / O4` | `add>add>divide` | `arithmetic:division_composition` | `percent` |
| `(4.4+3.8+3.3) / 3` | `( O1 + O2 + O3 ) / O4` | `add>add>divide` | `arithmetic:division_composition` | `percent` |
| `(924+967) / 2` | `( O1 + O2 ) / O3` | `add>divide` | `arithmetic:division_composition` | `million` |
| `(1,085+988) / 2` | `( O1 + O2 ) / O3` | `add>divide` | `arithmetic:division_composition` | `million` |

## Span / Multi-Span / Count / Comparison

- `span_lookup`: should form Strategy as evidence-location and value-normalization guidance, not arithmetic procedure.
- `multi_span_lookup`: should form Strategy for collecting multiple values/labels from table/text and preserving answer granularity.
- `count`: should form Strategy only as deterministic counting over listed conditions/items; support is smaller, so keep separate from arithmetic.
- `comparison`: should form Strategy as table/text comparison with direction and yes/no or span-like output handling. It is not equivalent to subtraction unless the question asks for a numeric difference.

Recommended non-arithmetic abstraction fields: `strategy_type`, `answer_from`, `scale`, `question_template`, `req_comparison`, and source evidence mode. Do not use answer strings as strategy text.

## Proposed Unified TAT-QA Strategy Schema

```json
{
  "strategy_id": "tatqa_strategy:<family_hash>",
  "dataset_id": "tatqa",
  "strategy_type": "arithmetic | span_lookup | multi_span_lookup | count | comparison",
  "family": "coarse deterministic family",
  "answer_from": "table | text | table-text",
  "scale": "none | percent | thousand | million | billion",
  "normalized_derivation": "O1 / O2, etc. for arithmetic only",
  "operator_sequence": ["subtract", "divide"],
  "operand_count": 2,
  "max_parenthesis_depth": 1,
  "question_template": "label-free question pattern for lookup strategies",
  "source_support_count": 123,
  "source_sample_ids": ["tatqa:train:..."],
  "retrieval_text": "label-free strategy description generated from schema fields only"
}
```

## Strategy Family Statistics

- Reliably abstractable train samples: 13215 (1.000).
- Coarse strategy families: 46.
- Schema families after including answer_from/scale: 127.
- Coarse family cumulative coverage: `{'top_5': 0.5891032917139614, 'top_10': 0.7732879303821415, 'top_20': 0.9552024214907302, 'top_50': 1.0, 'top_100': 1.0}`.
- Schema cumulative coverage: `{'top_5': 0.4033295497540674, 'top_10': 0.5662504729474083, 'top_20': 0.7919031403707908, 'top_50': 0.9710177828225501, 'top_100': 0.9975785092697692}`.

| Top family | Count | Rate |
|---|---:|---:|
| `span_lookup:text:scale=none` | 2704 | 0.205 |
| `arithmetic:difference` | 2151 | 0.163 |
| `arithmetic:percent_change` | 1268 | 0.096 |
| `arithmetic:division_composition` | 1071 | 0.081 |
| `comparison:table:scale=none` | 591 | 0.045 |
| `span_lookup:table-text:scale=thousand` | 574 | 0.043 |
| `multi_span_lookup:table-text:scale=none` | 558 | 0.042 |
| `arithmetic:ratio` | 519 | 0.039 |
| `span_lookup:table-text:scale=none` | 401 | 0.030 |
| `span_lookup:table:scale=none` | 382 | 0.029 |
| `multi_span_lookup:table:scale=none` | 368 | 0.028 |
| `span_lookup:table-text:scale=million` | 358 | 0.027 |
| `span_lookup:table:scale=million` | 290 | 0.022 |
| `arithmetic:sum` | 221 | 0.017 |
| `span_lookup:table:scale=thousand` | 219 | 0.017 |
| `multi_span_lookup:table-text:scale=thousand` | 218 | 0.016 |
| `count:table-text:scale=none` | 213 | 0.016 |
| `multi_span_lookup:text:scale=none` | 208 | 0.016 |
| `arithmetic:change_or_composed_ratio` | 160 | 0.012 |
| `comparison:table-text:scale=none` | 149 | 0.011 |

Top schema families:

| Schema family | Count | Rate |
|---|---:|---:|
| `span_lookup|span_lookup:text:scale=none|from=text|scale=none` | 2704 | 0.205 |
| `arithmetic|arithmetic:percent_change|from=table|scale=percent` | 903 | 0.068 |
| `comparison|comparison:table:scale=none|from=table|scale=none` | 591 | 0.045 |
| `span_lookup|span_lookup:table-text:scale=thousand|from=table-text|scale=thousand` | 574 | 0.043 |
| `multi_span_lookup|multi_span_lookup:table-text:scale=none|from=table-text|scale=none` | 558 | 0.042 |
| `arithmetic|arithmetic:difference|from=table|scale=million` | 516 | 0.039 |
| `arithmetic|arithmetic:difference|from=table-text|scale=thousand` | 486 | 0.037 |
| `span_lookup|span_lookup:table-text:scale=none|from=table-text|scale=none` | 401 | 0.030 |
| `span_lookup|span_lookup:table:scale=none|from=table|scale=none` | 382 | 0.029 |
| `multi_span_lookup|multi_span_lookup:table:scale=none|from=table|scale=none` | 368 | 0.028 |
| `span_lookup|span_lookup:table-text:scale=million|from=table-text|scale=million` | 358 | 0.027 |
| `arithmetic|arithmetic:difference|from=table|scale=thousand` | 344 | 0.026 |
| `arithmetic|arithmetic:percent_change|from=table-text|scale=percent` | 331 | 0.025 |
| `arithmetic|arithmetic:division_composition|from=table|scale=million` | 315 | 0.024 |
| `arithmetic|arithmetic:difference|from=table-text|scale=million` | 315 | 0.024 |
| `arithmetic|arithmetic:ratio|from=table|scale=percent` | 313 | 0.024 |
| `span_lookup|span_lookup:table:scale=million|from=table|scale=million` | 290 | 0.022 |
| `arithmetic|arithmetic:difference|from=table|scale=none` | 273 | 0.021 |
| `arithmetic|arithmetic:division_composition|from=table|scale=none` | 222 | 0.017 |
| `arithmetic|arithmetic:division_composition|from=table|scale=thousand` | 221 | 0.017 |

## Inclusion Recommendation

- Include arithmetic samples with non-empty derivation and at least one parsed operator as procedural strategies.
- Include span and multi-span as lookup/evidence selection strategies, not as arithmetic strategies.
- Include count and comparison as separate small strategy types; do not merge comparison into numeric difference unless the annotation is arithmetic.
- Exclude or mark low-confidence only samples with missing answer_type or arithmetic derivations that parse to no operator.

## LLM Abstraction Next Step

A small LLM pass is worth doing next, but only after freezing this deterministic schema. The highest-value use is semantic wording of strategy descriptions from schema fields and representative train examples, not inventing new families. Arithmetic formula families are already recoverable deterministically; span/comparison strategies need semantic abstraction for evidence-location cues.

Decision: `PROCEED TO SMALL-LLM TAT-QA STRATEGY ABSTRACTION PILOT`.
