# MultiHiertt Strategy Memory Pilot

Date: 2026-08-17

Scope: v0 small pilot only. Frozen deterministic family/schema from `multihiertt_strategy_structure_audit.py`; no reclustering, no retrieval audit, no four-arm experiment, no router.

## Construction

- Strategy coverage rule: top-12 coarse families + top-20 fine schema keys from the frozen structure audit.
- Total strategies: 32.
- Strategy levels: `{'coarse': 12, 'schema': 20}`.
- Strategy types: `{'program': 24, 'span_superlative_lookup': 3, 'span_comparison_lookup': 3, 'span_direct_lookup': 1, 'span_computed_value_lookup': 1}`.
- Generation counts: `{'llm_guidance_with_deterministic_structure': 32}`.
- Unique train samples covered by selected groups: 7431 / 7830 (0.949).
- Planned LLM calls: 32 with budget <= 32.
- Calls made in latest run: 0; cache hits: 32; cache records after run: 32.

Program strategies preserve deterministic operator sequence and normalized MultiHiertt DSL templates. The LLM only supplied reusable reasoning, evidence, scale, and multi-table guidance. Span strategies use LLM abstraction for lookup/comparison/superlative behavior.

## LLM Safety Contract

- Examples are structural and redacted: no raw question text, no paragraphs, no table text, no company names, no concrete years, no concrete numbers, no answers.
- Prompts include only frozen family/schema metadata, operator/template structure, evidence modality, scale hint, table/hierarchy flags, and 4-6 structural examples.
- The model is explicitly forbidden from solving examples or inventing new formula/family definitions.
- Raw cache path: `pilot/multibench/output/multihiertt/multihiertt_strategy_memory_v0_llm_cache.jsonl`. It is ignored by git; audit JSON records cache keys and runtime summary.

## Offline QC

- Schema legal rate: 1.000.
- Leak failures: 0.
- Duplicate strategy ids: 0.
- Duplicate descriptions: 0.
- Duplicate retrieval texts: 0.

The leak scan checks generated semantic text and structural examples for concrete years, currency/large numeric values, decimals, and standalone numbers beyond trivial placeholders. It is conservative text QC, not proof of semantic anonymity.

## Sample Strategies

### multihiertt_strategy:2245d693d25dd1bd

- level: `coarse`
- type: `program`
- family: `program:aggregation_sum`
- schema: `coarse:program:aggregation_sum`
- support: 2011
- operators: `add`
- template: `add(<operand>, <operand>)`
- description: This strategy applies when a question asks for the total or combined amount of two or more component values that are explicitly provided in text or in hierarchical table cells, and the answer is obtained by simple addition.
- reasoning: Identify the exact operands from the question and map them to the evidence values; do not infer or estimate missing values.; Perform the addition in the order given by the template, but since addition is commutative, order does not affect the result.; If the question implies a total but only one component is given, do not attempt to derive the other; the strategy requires all operands to be present.
- evidence: Locate the two or more component values that are named or implied by the question; they may appear in text sentences or as leaf cells under a common parent row/column in a table.; If the table has hierarchy markers (e.g., indentation, subtotal rows, or parent-child labels), use those markers to confirm which cells are the direct components and not the parent total.; When evidence spans multiple tables, check that the component values come from the same reporting period or context; if not, note the mismatch and avoid combining them.
- risks: Risk of using a parent total instead of its child components, leading to double counting.; Risk of mixing values with different units or scales (e.g., thousands vs. millions) without conversion.; Risk of ignoring hierarchy markers and adding a subtotal along with its components.

### multihiertt_strategy:fbf259ef9cea6db8

- level: `coarse`
- type: `program`
- family: `program:change_rate`
- schema: `coarse:program:change_rate`
- support: 1441
- operators: `subtract>divide`
- template: `subtract(<operand>, <operand>), divide(<result>, <operand>)`
- description: This strategy applies when a question asks for the rate of change (percentage increase or decrease) of a metric, where the change is computed by subtracting a base value from a target value and then dividing the difference by the base value. The evidence is typically found in a single hierarchical table, but may also involve text or a combination.
- reasoning: Identify the two values that represent the 'before' and 'after' states for the metric in question.; Compute the absolute change by subtracting the base value from the target value.; Divide the absolute change by the base value to obtain the rate, then express as a percentage if required.; Ensure the order of subtraction is correct: the value in the later period or the 'new' category is the target, and the earlier or 'old' is the base.
- evidence: Locate the table rows or columns that contain the target metric and the base period or category values; use hierarchy markers to identify parent-child relationships.; If text is involved, search for explicit statements of values or changes that correspond to the metric and period in question.; Ensure that the identified values are directly comparable (same units, same scope) before using them in the calculation.
- risks: Misidentifying which value is the base can lead to an inverted or incorrect percentage.; Ignoring hierarchy markers may cause using a subtotal instead of a leaf value, or vice versa.; Failing to convert the result to a percentage when the scale hint indicates 'percent' will produce a wrong answer format.

### multihiertt_strategy:c3f0f4b0cac29d3e

- level: `coarse`
- type: `program`
- family: `program:average_or_composed_division`
- schema: `coarse:program:average_or_composed_division`
- support: 1137
- operators: `add>divide`
- template: `add(<operand>, <operand>), divide(<result>, <const>)`
- description: Use this strategy when the question requires summing two or more component values and then dividing the total by a constant (e.g., a count, a number of periods, or a fixed divisor) to obtain an average or a composed per-unit figure.
- reasoning: Identify all components that the question implies should be added together; ensure they are at the same granularity and not overlapping.; Sum the components to get a total, then divide by the constant divisor as specified by the question's wording (e.g., 'average', 'per', 'each').; If the divisor is not explicitly given, infer it from the context (e.g., number of periods, number of categories) but do not assume without evidence.; Check whether the division should be performed after the sum or if any intermediate scaling (e.g., converting to millions) is needed.
- evidence: Locate the component values in the table rows or text segments that correspond to the categories or periods named in the question.; If the table has hierarchical markers (e.g., subtotals, indentation, or parent-child labels), ensure that the selected components are at the same level and do not double-count any subtotal.; For text evidence, identify explicit mentions of the components and any stated constant divisor (e.g., 'over X years' or 'per Y units').; When multiple tables are present, check whether the components are split across tables and whether the divisor is stated in one table or in the text.
- risks: Risk of double-counting when using hierarchical table rows: ensure that subtotals are not added together with their child components.; Risk of misidentifying the divisor: the constant may be a count of items, a number of years, or a scalar; verify from the question or context.; Risk of scale mismatch: if components are in different units (e.g., thousands vs. millions), convert before summing to avoid incorrect totals.

### multihiertt_strategy:91242648d6faed4e

- level: `coarse`
- type: `span_superlative_lookup`
- family: `span:superlative_lookup`
- schema: `coarse:span:superlative_lookup`
- support: 556
- operators: `none`
- template: ``
- description: Use when a question asks for the entity, period, or category that holds the highest or lowest value of a given metric, and the answer is a direct span from the table rather than a computed result.
- reasoning: Parse the question to identify the target metric and the superlative direction (max or min).; Scan the table to find the column or row corresponding to the target metric, then compare values across the relevant comparison set.; Select the label associated with the extreme value; ensure the label is taken from the same row/column as the extreme value.; If the table uses hierarchical markers, verify that the selected label is at the correct level (e.g., not a subtotal when comparing individual items).
- evidence: Locate the table that contains the metric named in the question; confirm the metric column and its unit/scale.; Identify the rows or columns that represent the comparison set (e.g., different periods, segments, or entities).; If the table has hierarchical markers (e.g., subtotals, indentation, or parent-child labels), ensure the comparison is among the intended level, not across levels.; Check for any accompanying text that may clarify the scope or definition of the metric before selecting the extreme.
- risks: Misinterpreting the comparison set: including subtotals or parent rows when only leaf-level items are intended, or vice versa.; Overlooking scale or unit differences: values may be in different units (e.g., thousands vs. millions) across rows or columns; ensure consistent comparison.; Selecting a label that is not directly associated with the extreme value due to merged cells or hierarchical indentation.

### multihiertt_strategy:5df905c0e6235174

- level: `coarse`
- type: `span_comparison_lookup`
- family: `span:comparison_lookup`
- schema: `coarse:span:comparison_lookup`
- support: 528
- operators: `none`
- template: ``
- description: This strategy applies when the question asks for a specific value that can be found by locating and comparing entries within a single table, often using hierarchical row or column labels to disambiguate the correct cell.
- reasoning: Parse the question to extract the target metric, time period, and any qualifying conditions (e.g., 'as of', 'for the year').; Locate the corresponding row and column in the table, using hierarchical labels to navigate to the correct level of detail.; Read the value directly from the cell; do not perform any arithmetic or transformation unless the question explicitly asks for it.; If the question implies a comparison (e.g., 'compared to'), still treat it as a lookup of the specific value requested, not a calculation.
- evidence: Identify the table that contains the relevant metric and time period; use the question's keywords to match row and column headers.; Look for hierarchical markers (e.g., indented rows, subtotal labels, grouped columns) to ensure the selected cell corresponds to the exact level of aggregation requested.; If text evidence is present, use it to confirm the table's context or to clarify ambiguous labels, but the final value should come from the table cell.
- risks: Misinterpreting hierarchical labels can lead to selecting a subtotal or parent row instead of the specific line item.; Ignoring scale hints (e.g., thousands, millions) may cause the answer to be off by a factor of a thousand.; Assuming a comparison is needed when the question only asks for a single value can introduce unnecessary errors.

### multihiertt_strategy:019ee514f46efe63

- level: `coarse`
- type: `program`
- family: `program:ratio`
- schema: `coarse:program:ratio`
- support: 415
- operators: `divide`
- template: `divide(<operand>, <operand>)`
- description: This strategy applies when a question asks for a ratio derived by dividing one financial quantity by another, where both quantities are explicitly stated or can be directly extracted from text or tables, and no additional computation steps are required.
- reasoning: Identify the two operands from the evidence, ensuring they refer to the same context (e.g., same period, same segment).; Perform the division in the order implied by the question phrasing (e.g., 'X per Y' means X divided by Y).; If the result is expected as a percentage, multiply the raw quotient by a numeric value; otherwise, express as a decimal or ratio.
- evidence: Locate the two quantities that serve as the numerator and denominator; they may appear as explicit numbers in text or as cell values in a table.; If using a table, identify the relevant row and column headers to ensure the correct values are selected, especially when hierarchical headers are present.; For text evidence, search for phrases that directly state the two quantities, often in close proximity or in the same sentence/paragraph.
- risks: Misidentifying which operand is the numerator versus the denominator, leading to an inverted ratio.; Selecting values from different hierarchical levels (e.g., using a subtotal instead of a leaf-level value) without proper justification.; Ignoring scale differences (e.g., thousands vs. millions) that could distort the ratio if not normalized.

### multihiertt_strategy:4a86fd0af1b41179

- level: `coarse`
- type: `program`
- family: `program:projection_or_compound_change`
- schema: `coarse:program:projection_or_compound_change`
- support: 404
- operators: `subtract>divide>add>multiply`
- template: `subtract(<operand>, <operand>), divide(<result>, <operand>), add(<const>, <result>), multiply(<operand>, <result>)`
- description: This strategy applies when a question requires deriving a projected or compound change by first computing a difference between two values, converting that difference into a rate or ratio, then adjusting a base value by a constant and scaling by another factor.
- reasoning: First, subtract the comparison value from the target metric to get an absolute difference.; Divide that difference by the base period value to obtain a rate or ratio.; Add a constant to the ratio, then multiply by a scaling factor to reach the final result.; Ensure the order of operations matches the template exactly; do not reorder or combine steps.
- evidence: Locate the two values needed for the initial subtraction, often found in a hierarchical table under different time periods or categories.; Identify the base value that will be divided into the difference to produce a ratio or percentage.; Find the constant to be added and the final multiplier, which may appear in the text or as a separate table entry.
- risks: Misidentifying which operand is the base for division can invert the ratio.; Ignoring hierarchy markers may lead to using a subtotal instead of a leaf value.; Applying the constant addition before the division changes the result; follow the sequence strictly.

### multihiertt_strategy:48d4e24e0a94be8c

- level: `coarse`
- type: `program`
- family: `program:difference`
- schema: `coarse:program:difference`
- support: 243
- operators: `subtract`
- template: `subtract(<operand>, <operand>)`
- description: This strategy applies when a question asks for the difference between two specific financial figures, each of which can be located as a single value in a table or text, and the operation is a straightforward subtraction.
- reasoning: Parse the question to identify the two values to be subtracted, ensuring they refer to the same metric and comparable units.; Locate each operand independently, using the question's descriptors to match the correct row/column or sentence.; Perform the subtraction in the order implied by the question (e.g., 'how much more' implies later minus earlier, but the strategy is symmetric).; Report the result as an absolute difference unless the question explicitly asks for a signed value.
- evidence: Identify the two operands by their semantic roles (e.g., target metric, base period) and locate each value in the table or text, respecting any hierarchical row/column headers.; If evidence is in a table, use the hierarchy markers (e.g., indentation, subtotal labels) to ensure the correct level of aggregation for each operand.; If evidence is in text, extract the numeric value associated with the exact metric and period/entity mentioned in the question.; When both text and table are present, prefer the table for numeric precision but cross-check with text for context or clarifications.
- risks: Misidentifying the operands due to similar metric names or overlapping categories in hierarchical tables.; Ignoring scale differences (e.g., one value in thousands, another in millions) leading to incorrect subtraction.; Selecting a subtotal instead of a leaf value, or vice versa, when the question targets a specific line item.

### multihiertt_strategy:54d9e148c52fb02a

- level: `coarse`
- type: `program`
- family: `program:division_composition`
- schema: `coarse:program:division_composition`
- support: 212
- operators: `divide`
- template: `divide(<operand>, <operand>)`
- description: Use this strategy when the question requires dividing one financial quantity by another to obtain a ratio, rate, or per-unit measure, and the evidence may come from text, tables, or both, with possible hierarchical table structures.
- reasoning: Identify which quantity is the numerator and which is the denominator based on the question's phrasing (e.g., 'per', 'as a percentage of', 'ratio of X to Y').; If the question involves a scale hint (e.g., million, percent), apply the appropriate conversion after performing the division, or adjust the operands before dividing to maintain consistency.; For multi-step cases, first compute any intermediate products or sums, then perform the final division; ensure the order of operations matches the normalized program template.
- evidence: Locate the two quantities that serve as the numerator and denominator; they may be explicitly stated in text or found in table cells, often under labeled rows or columns.; If tables are used, identify the relevant row and column headers, and follow any hierarchy markers (e.g., indentation, subtotals, parent-child labels) to ensure you select the correct level of aggregation.; When evidence is mixed, cross-check text statements against table values to confirm the same underlying figures are being referenced.
- risks: Misidentifying the numerator and denominator can invert the ratio; always verify the question's intent.; Ignoring hierarchy markers may lead to using a subtotal instead of a line item, or vice versa, causing incorrect values.; Failing to apply scale conversions (e.g., mixing millions with thousands) can produce results off by a factor of a thousand or more.

### multihiertt_strategy:6a365124717069aa

- level: `coarse`
- type: `span_direct_lookup`
- family: `span:direct_lookup`
- schema: `coarse:span:direct_lookup`
- support: 164
- operators: `none`
- template: ``
- description: Use when the question asks for a specific value or label that appears verbatim in a single table cell or a contiguous text span, and no arithmetic, aggregation, or multi-step reasoning is required.
- reasoning: Match the question's key terms (metric, period, entity) to the table's row/column labels or text's noun phrases.; Follow the hierarchical header structure from top-level to leaf to confirm the exact cell or span.; Do not perform any arithmetic; the answer is the raw value as presented.; If the question includes a scale hint (e.g., 'in millions'), verify the table's stated unit matches; if not, report the value as-is without conversion.
- evidence: Locate the table or text passage that contains the exact metric or label named in the question.; Identify the row and column intersection (or sentence span) that directly corresponds to the requested item.; If the table has hierarchical row/column headers, use the parent headers to disambiguate which cell is the correct target.; For text+table cases, check both modalities; the answer may be in a table cell or in a nearby text sentence that repeats the same value.
- risks: Misreading hierarchical headers can lead to selecting a parent aggregate instead of the leaf-level value.; Ambiguity between text and table values may cause picking the wrong modality; cross-check if both are present.; Scale mismatches (e.g., table in thousands but question implies millions) can cause misinterpretation, but do not convert—report the literal value.

### multihiertt_strategy:b72171a6cd389886

- level: `coarse`
- type: `span_computed_value_lookup`
- family: `span:computed_value_lookup`
- schema: `coarse:span:computed_value_lookup`
- support: 162
- operators: `none`
- template: ``
- description: Use when the question asks for a specific metric value that is already present in the table or text, and the answer is simply that value without any arithmetic.
- reasoning: Match the question's metric and period to the table's row and column headers, using hierarchy to resolve ambiguity.; If the value is not directly in a cell, check text near the table for a stated figure that matches the question.; Do not perform any arithmetic; the answer is the exact value as presented.
- evidence: Locate the table row and column that match the metric and period named in the question.; If the table has hierarchical row or column headers, follow the hierarchy to find the most specific matching cell.; Check the surrounding text for any qualifiers (e.g., 'as of', 'for the year') that disambiguate the exact value.
- risks: Misreading hierarchical headers can lead to selecting a parent total instead of the specific child value.; Ignoring scale hints (e.g., 'in millions') may cause the answer to be off by a factor.; If the question uses synonyms for the metric, ensure the table header matches the intended concept.

### multihiertt_strategy:0a5af34422326419

- level: `coarse`
- type: `program`
- family: `program:difference_composition`
- schema: `coarse:program:difference_composition`
- support: 158
- operators: `add>subtract`
- template: `add(<operand>, <operand>), subtract(<result>, <operand>)`
- description: This strategy applies when a target metric must be derived by first combining two component values (via addition or subtraction) and then adjusting that intermediate result by another component value (via subtraction or addition), typically to isolate a residual or net figure from hierarchical financial data.
- reasoning: First, determine the initial operation (add or subtract) and identify the two operands that produce the intermediate result; ensure the order matches the template.; Then, apply the second operation (subtract or add) using the intermediate result and the third operand; verify that the operation direction is correct as per the template.; Throughout, maintain the scale and unit consistency; do not convert or round until the final step unless the question specifies otherwise.
- evidence: Locate the primary table containing the target metric and its components, using hierarchy markers (e.g., indentation, subtotal labels) to identify parent-child relationships.; Identify text passages that define or clarify the components, especially if the table lacks explicit labels for the needed operands.; Cross-check that all operands are drawn from the same reporting period and scope; do not mix values from different columns or sections unless the question explicitly requires it.
- risks: Misidentifying which rows are subtotals versus components can lead to using the wrong operands.; Ignoring hierarchy markers may cause double-counting or omitting a needed component.; Applying the operations in the wrong order (e.g., subtracting before adding) will produce an incorrect result.

## QC Interpretation

The v0 pool is intentionally small and high-support. Coarse strategies provide broad recall over common reasoning families, while schema strategies retain evidence modality, table usage, scale hint, and step-count specificity for retrieval experiments.

Known limitations:

- The pool is not intended to cover the fine-schema long tail.
- LLM semantic guidance is exploratory and must be validated by retrieval-only audit before any execution experiment.
- The automatic leakage scan cannot detect every company/entity mention, but prompts do not expose raw company/report text.

## Decision

Decision: `READY FOR STRATEGY RETRIEVAL AUDIT`.
