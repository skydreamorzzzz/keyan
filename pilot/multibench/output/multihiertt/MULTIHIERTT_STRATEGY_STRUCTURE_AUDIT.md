# MultiHiertt Strategy Structure Audit

Date: 2026-08-17

Scope: deterministic offline structure audit over MultiHiertt train only. No LLM/API calls, no Strategy Memory generation, no retrieval, no four-arm experiment, no router.

## Train Distribution

- Train samples: 7830.
- Program/span: program 6306 / span 1524.
- Answer type counts: `{'program': 6306, 'span': 1524}`.
- Evidence modality: `{'text+table': 4209, 'table': 2908, 'text': 713}`.
- Table evidence usage: `{'single_table': 5586, 'multi_table': 1531, 'no_table_evidence': 713}`.
- HTML hierarchy markers: `{'has_hierarchy': 7263, 'no_hierarchy': 567}`.

## Program Structure

- Program samples retain the original MultiHiertt flat DSL. This audit extracts structure for grouping only; it does not convert programs into FinQA DSL.
- Operator family counts: `{'add': 2011, 'none': 1524, 'divide+subtract': 1481, 'add+divide': 1123, 'divide': 546, 'add+divide+multiply+subtract': 373, 'subtract': 284, 'multiply': 121, 'add+divide+subtract': 104, 'add+subtract': 100, 'divide+multiply': 81, 'divide+multiply+subtract': 23, 'add+multiply': 18, 'multiply+subtract': 15, 'add+divide+multiply': 14, 'add+divide+exp+multiply+subtract': 8, 'add+exp+multiply': 2, 'exp+multiply+subtract': 1, 'add+multiply+subtract': 1}`.
- Step-count buckets: `{'2': 2969, '0': 1524, '5plus': 294, '1': 1979, '4': 492, '3': 572}`.
- Operand-count buckets: `{'3': 2968, '0': 1524, '7': 53, '2': 1981, '5': 490, '4': 572, '9plus': 83, '6': 129, '8': 30}`.

Top operator sequences:

| Operator sequence | Count | Rate |
|---|---:|---:|
| `none` | 1524 | 0.195 |
| `subtract>divide` | 1425 | 0.182 |
| `add` | 1092 | 0.139 |
| `add>divide` | 739 | 0.094 |
| `add>add` | 592 | 0.076 |
| `divide` | 527 | 0.067 |
| `subtract>divide>add>multiply` | 330 | 0.042 |
| `add>add>divide` | 248 | 0.032 |
| `subtract` | 243 | 0.031 |
| `add>add>add` | 202 | 0.026 |
| `multiply` | 117 | 0.015 |
| `multiply>divide` | 63 | 0.008 |
| `add>add>add>divide` | 49 | 0.006 |
| `add>add>add>add` | 42 | 0.005 |
| `add>add>add>add>add` | 40 | 0.005 |
| `add>add>add>add>divide` | 37 | 0.005 |
| `subtract>subtract` | 31 | 0.004 |
| `divide>subtract` | 29 | 0.004 |
| `subtract>multiply>divide>add` | 25 | 0.003 |
| `divide>divide` | 19 | 0.002 |

## Span Structure

- Span samples are kept separate from program schema.
- Deterministic span families use question intent only: direct lookup, comparison yes/no, comparison lookup, superlative lookup, multi-value lookup, and computed-value lookup.
- Span family labels are for Strategy design/audit, not official answer_type fields.

## Family Coverage

- Coarse families: 17.
- Fine schema families: 414.
- Coarse cumulative coverage: `{'top_5': 0.7245210727969349, 'top_10': 0.9081736909323116, 'top_15': 0.9950191570881226, 'top_20': 1.0, 'top_30': 1.0, 'top_50': 1.0}`.
- Schema cumulative coverage: `{'top_5': 0.19923371647509577, 'top_10': 0.33729246487867176, 'top_20': 0.49808429118773945, 'top_30': 0.5928480204342274, 'top_50': 0.7134099616858237, 'top_100': 0.8629629629629629}`.

Top coarse families:

| Family | Count | Rate |
|---|---:|---:|
| `program:aggregation_sum` | 2011 | 0.257 |
| `program:change_rate` | 1441 | 0.184 |
| `program:average_or_composed_division` | 1137 | 0.145 |
| `span:superlative_lookup` | 556 | 0.071 |
| `span:comparison_lookup` | 528 | 0.067 |
| `program:ratio` | 415 | 0.053 |
| `program:projection_or_compound_change` | 404 | 0.052 |
| `program:difference` | 243 | 0.031 |
| `program:division_composition` | 212 | 0.027 |
| `span:direct_lookup` | 164 | 0.021 |
| `span:computed_value_lookup` | 162 | 0.021 |
| `program:difference_composition` | 158 | 0.020 |
| `program:difference_then_ratio` | 144 | 0.018 |
| `program:multiplication` | 117 | 0.015 |
| `span:comparison_yesno` | 99 | 0.013 |
| `program:multiplication_composition` | 24 | 0.003 |
| `span:multi_value_lookup` | 15 | 0.002 |

Top fine schema families:

| Schema key | Count | Rate |
|---|---:|---:|
| `program|program:change_rate|ops=divide+subtract|steps=2|ev=text+table|tables=single|scale=none` | 407 | 0.052 |
| `program|program:change_rate|ops=divide+subtract|steps=2|ev=table|tables=single|scale=none` | 300 | 0.038 |
| `span|span:superlative_lookup|ops=none|steps=0|ev=text+table|tables=single|scale=none` | 297 | 0.038 |
| `program|program:change_rate|ops=divide+subtract|steps=2|ev=table|tables=single|scale=percent` | 296 | 0.038 |
| `program|program:aggregation_sum|ops=add|steps=1|ev=table|tables=multi|scale=none` | 260 | 0.033 |
| `span|span:comparison_lookup|ops=none|steps=0|ev=text+table|tables=single|scale=none` | 224 | 0.029 |
| `program|program:aggregation_sum|ops=add|steps=2|ev=text+table|tables=multi|scale=none` | 223 | 0.028 |
| `program|program:average_or_composed_division|ops=add+divide|steps=2|ev=table|tables=multi|scale=none` | 220 | 0.028 |
| `program|program:average_or_composed_division|ops=add+divide|steps=2|ev=text+table|tables=multi|scale=none` | 212 | 0.027 |
| `program|program:aggregation_sum|ops=add|steps=1|ev=text+table|tables=multi|scale=none` | 202 | 0.026 |
| `program|program:aggregation_sum|ops=add|steps=1|ev=text+table|tables=single|scale=million` | 182 | 0.023 |
| `program|program:projection_or_compound_change|ops=add+divide+multiply+subtract|steps=4|ev=text+table|tables=single|scale=million` | 166 | 0.021 |
| `span|span:superlative_lookup|ops=none|steps=0|ev=table|tables=single|scale=none` | 156 | 0.020 |
| `program|program:change_rate|ops=divide+subtract|steps=2|ev=text|tables=none|scale=percent` | 138 | 0.018 |
| `span|span:comparison_lookup|ops=none|steps=0|ev=table|tables=single|scale=none` | 125 | 0.016 |
| `program|program:aggregation_sum|ops=add|steps=1|ev=table|tables=single|scale=million` | 115 | 0.015 |
| `program|program:change_rate|ops=divide+subtract|steps=2|ev=text+table|tables=single|scale=percent` | 104 | 0.013 |
| `program|program:ratio|ops=divide|steps=1|ev=text+table|tables=single|scale=percent` | 94 | 0.012 |
| `program|program:projection_or_compound_change|ops=add+divide+multiply+subtract|steps=4|ev=table|tables=single|scale=million` | 90 | 0.011 |
| `program|program:aggregation_sum|ops=add|steps=2|ev=text+table|tables=single|scale=million` | 89 | 0.011 |
| `program|program:aggregation_sum|ops=add|steps=1|ev=text+table|tables=multi|scale=million` | 84 | 0.011 |
| `program|program:ratio|ops=divide|steps=1|ev=text|tables=none|scale=percent` | 79 | 0.010 |
| `span|span:direct_lookup|ops=none|steps=0|ev=text+table|tables=single|scale=none` | 77 | 0.010 |
| `program|program:aggregation_sum|ops=add|steps=3|ev=text+table|tables=single|scale=million` | 77 | 0.010 |
| `program|program:ratio|ops=divide|steps=1|ev=text+table|tables=single|scale=none` | 76 | 0.010 |

## Top Joint Patterns

| Family | Operator family | Steps | Evidence | Tables | Scale | Count | Rate |
|---|---|---:|---|---|---|---:|---:|
| `program:change_rate` | `divide+subtract` | `2` | `text+table` | `single_table` | `none` | 407 | 0.052 |
| `program:change_rate` | `divide+subtract` | `2` | `table` | `single_table` | `none` | 300 | 0.038 |
| `span:superlative_lookup` | `none` | `0` | `text+table` | `single_table` | `none` | 297 | 0.038 |
| `program:change_rate` | `divide+subtract` | `2` | `table` | `single_table` | `percent` | 296 | 0.038 |
| `program:aggregation_sum` | `add` | `1` | `table` | `multi_table` | `none` | 260 | 0.033 |
| `span:comparison_lookup` | `none` | `0` | `text+table` | `single_table` | `none` | 224 | 0.029 |
| `program:aggregation_sum` | `add` | `2` | `text+table` | `multi_table` | `none` | 223 | 0.028 |
| `program:average_or_composed_division` | `add+divide` | `2` | `table` | `multi_table` | `none` | 220 | 0.028 |
| `program:average_or_composed_division` | `add+divide` | `2` | `text+table` | `multi_table` | `none` | 212 | 0.027 |
| `program:aggregation_sum` | `add` | `1` | `text+table` | `multi_table` | `none` | 202 | 0.026 |
| `program:aggregation_sum` | `add` | `1` | `text+table` | `single_table` | `million` | 182 | 0.023 |
| `program:projection_or_compound_change` | `add+divide+multiply+subtract` | `4` | `text+table` | `single_table` | `million` | 166 | 0.021 |
| `span:superlative_lookup` | `none` | `0` | `table` | `single_table` | `none` | 156 | 0.020 |
| `program:change_rate` | `divide+subtract` | `2` | `text` | `no_table` | `percent` | 138 | 0.018 |
| `span:comparison_lookup` | `none` | `0` | `table` | `single_table` | `none` | 125 | 0.016 |
| `program:aggregation_sum` | `add` | `1` | `table` | `single_table` | `million` | 115 | 0.015 |
| `program:change_rate` | `divide+subtract` | `2` | `text+table` | `single_table` | `percent` | 104 | 0.013 |
| `program:ratio` | `divide` | `1` | `text+table` | `single_table` | `percent` | 94 | 0.012 |
| `program:projection_or_compound_change` | `add+divide+multiply+subtract` | `4` | `table` | `single_table` | `million` | 90 | 0.011 |
| `program:aggregation_sum` | `add` | `2` | `text+table` | `single_table` | `million` | 89 | 0.011 |

## Program Examples

| Family | Operators | Steps | Operands | Evidence | Tables | Template |
|---|---|---:|---:|---|---|---|
| `program:average_or_composed_division` | `add>divide` | 2 | 3 | `text+table` | `single` | `add(<operand>, <operand>), divide(<result>, <const>)` |
| `program:difference` | `subtract` | 1 | 2 | `table` | `single` | `subtract(<operand>, <operand>)` |
| `program:aggregation_sum` | `add` | 1 | 2 | `text+table` | `multi` | `add(<operand>, <operand>)` |
| `program:ratio` | `divide` | 1 | 2 | `text` | `none` | `divide(<operand>, <operand>)` |
| `program:projection_or_compound_change` | `subtract>divide>add>multiply` | 4 | 5 | `text+table` | `single` | `subtract(<operand>, <operand>), divide(<result>, <operand>), add(<const>, <result>), multiply(<operand>, <result>)` |
| `program:change_rate` | `subtract>divide` | 2 | 3 | `table` | `single` | `subtract(<operand>, <operand>), divide(<result>, <operand>)` |
| `program:division_composition` | `divide` | 1 | 2 | `text` | `none` | `divide(<operand>, <operand>)` |
| `program:multiplication` | `multiply` | 1 | 2 | `table` | `single` | `multiply(<operand>, <operand>)` |
| `program:difference_then_ratio` | `subtract>divide` | 2 | 3 | `table` | `single` | `subtract(<operand>, <operand>), divide(<result>, <operand>)` |
| `program:difference_composition` | `add>subtract` | 2 | 3 | `text+table` | `single` | `add(<operand>, <operand>), subtract(<result>, <operand>)` |

## Span Examples

| Family | Evidence | Tables | Scale | Question template |
|---|---|---|---|---|
| `span:superlative_lookup` | `table` | `single` | `million` | `what's the greatest value of consumer in <year>? (in million)` |
| `span:computed_value_lookup` | `text+table` | `single` | `none` | `without management and financial advice fees and other revenues, how much of revenue is there in total in <year> (in milion)` |
| `span:comparison_lookup` | `text+table` | `single` | `thousand` | `what's the sum of all reimbursementagreements that are greater than <num> in partner type? (in thousand)` |
| `span:direct_lookup` | `table` | `single` | `none` | `how many elements show negative value in<num> forvies ?` |
| `span:comparison_yesno` | `table` | `single` | `none` | `does the value of total core deposits in <year> greater than that in <year>?` |
| `span:multi_value_lookup` | `text+table` | `single` | `none` | `in which year is loans and leases outstanding positive?` |

## Recommended Strategy Schema

```json
{
  "strategy_id": "multihiertt_strategy:<family_hash>",
  "dataset_id": "multihiertt",
  "strategy_type": "program | span_lookup | span_comparison | span_superlative | span_multi_value",
  "family": "coarse deterministic family",
  "schema_key": "answer_type + family + operator_family + step bucket + evidence modality + table usage + scale hint",
  "program_dsl": "multihiertt_original_flat_dsl_for_program_families",
  "operator_sequence": [
    "add",
    "divide"
  ],
  "operator_family": "add+divide",
  "step_count_bucket": "0 | 1 | 2 | 3 | 4 | 5plus",
  "operand_count_bucket": "0..8 | 9plus",
  "evidence_modality": "text | table | text+table | none",
  "table_usage": {
    "table_count": "document table count",
    "evidence_table_count": "number of unique table ids in gold table evidence",
    "multi_table_evidence": "bool",
    "hierarchy_marker_count": "rowspan/colspan/th marker count from HTML"
  },
  "scale_hint": "none | percent | thousand | million | billion",
  "normalized_program_template": "program with numeric literals/references replaced by <operand>",
  "span_question_template": "label-free normalized question pattern for span families",
  "source_support_count": 123,
  "source_sample_ids": [
    "multihiertt:train:..."
  ],
  "retrieval_text": "future semantic abstraction, generated without concrete company/year/number/answer leakage"
}
```

## Small-LLM Pilot Family Set

- Selection rule: top 12 coarse families plus top 20 schema keys by train support; fixed before any LLM abstraction.
- Estimated coarse coverage: 0.949.
- Estimated schema coverage: 0.498.
- Recommended examples per family: 4-6 representative train examples in next round, with company/year/number/answer redaction.

Coarse families to cover first:

- `program:aggregation_sum`: 2011
- `program:change_rate`: 1441
- `program:average_or_composed_division`: 1137
- `span:superlative_lookup`: 556
- `span:comparison_lookup`: 528
- `program:ratio`: 415
- `program:projection_or_compound_change`: 404
- `program:difference`: 243
- `program:division_composition`: 212
- `span:direct_lookup`: 164
- `span:computed_value_lookup`: 162
- `program:difference_composition`: 158

## Recommendation

- Program strategies should be generated from deterministic schema plus original MultiHiertt DSL structure; do not ask an LLM to invent formulas.
- Span strategies should be semantic evidence-location strategies, with comparison/superlative/direct lookup kept separate from arithmetic.
- Multi-table and hierarchy usage should be explicit strategy metadata because MultiHiertt often requires linking evidence across several HTML tables.
- The next LLM pilot should only abstract high-support families into reusable reasoning/evidence-location descriptions with company names, years, numbers, and answers redacted.

## Decision

Decision: `PROCEED SMALL-LLM STRATEGY PILOT`.
