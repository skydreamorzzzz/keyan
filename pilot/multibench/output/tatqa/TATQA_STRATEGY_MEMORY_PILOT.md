# TAT-QA Strategy Memory Pilot

Date: 2026-08-16

Scope: v0 small pilot only. Frozen deterministic schema from `tatqa_strategy_structure_audit.py`; no reclustering, no family retuning, no retrieval audit, no four-arm experiment, no router.

## Construction

- Strategy unit: top-30 frozen schema families by train support.
- Total strategies: 30.
- Train support covered: 12057 / 13215 (0.912).
- Top-30 schema support rate: 0.912.
- Generation counts: `{'llm_semantic_abstraction': 15, 'deterministic_arithmetic_template': 15}`.
- Strategy type counts: `{'span_lookup': 7, 'arithmetic': 15, 'comparison': 2, 'multi_span_lookup': 5, 'count': 1}`.
- LLM cache records: 15 for 15 planned semantic abstractions; budget: <= 20.
- Calls made in the most recent build command: 0; cache hits: 15.

Arithmetic strategies were generated directly from deterministic structure templates. High-frequency `span_lookup`, `multi_span_lookup`, `count`, and `comparison` schema families used one LLM semantic abstraction call per schema, with 4-6 sanitized representative question templates.

## LLM Safety Contract

- Prompt examples contain sanitized question templates only; concrete numbers and years are replaced upstream.
- Prompts exclude answer strings, derivations, table values, paragraphs, company names, and raw report text.
- The model is asked only for evidence locating, operand roles, answer form, scale notes, and risks.
- Raw responses are cached in `pilot/multibench/output/tatqa/tatqa_strategy_memory_v0_llm_cache.jsonl`.

## Offline QC

- Schema legal rate: 1.000.
- Leak failures: 0.
- Duplicate descriptions: 11.
- Duplicate retrieval texts: 0.

The leak scan checks generated semantic text for concrete years, currency/large numeric values, decimals, and standalone numbers beyond trivial placeholders. It is a conservative text scan, not proof of semantic anonymity.

## Sample Strategies

### tatqa_strategy:c6a4ddd06d027da3

- schema: `span_lookup|span_lookup:text:scale=none|from=text|scale=none`
- support: 2704
- method: `llm_semantic_abstraction`
- description: Use this strategy when a question asks for the reason behind a change, trend, or accounting practice, and the answer is explicitly stated in the text rather than requiring calculation or table lookup.
- evidence: Search for sentences containing causal connectors such as 'due to', 'because of', 'resulting from', or 'primarily attributable to'.; Look near the reported metric or item mentioned in the question, often in the same paragraph or adjacent section.; Prioritize management discussion or notes sections where explanations are typically provided.; If the question references a change between two periods, locate the paragraph discussing that specific change.
- roles: metric label: the financial or operational item whose change or treatment is questioned; reporting period: the time frame(s) mentioned in the question, used to narrow the search; causal factor: the underlying reason or event described in the text; context qualifier: any additional descriptors (e.g., segment, product line) that refine the scope
- scale: No numeric scale is involved; the answer is purely textual.; Do not convert or normalize any units; ignore magnitude unless it is part of the causal explanation.; If the text mentions percentages or amounts, treat them as supporting context, not as the answer itself.

### tatqa_strategy:0558c413ad491400

- schema: `arithmetic|arithmetic:percent_change|from=table|scale=percent`
- support: 903
- method: `deterministic_arithmetic_template`
- description: Use when the question asks for relative change between a new value and a prior/base value.
- evidence: Locate the same metric for the compared periods or conditions.; Use the newer/current value as the changed amount endpoint and the prior/base value as denominator.
- roles: new_or_current_value; prior_or_base_value; metric_label
- scale: Treat percent output carefully; distinguish percentage points from percent change.

### tatqa_strategy:23fb96da95dead74

- schema: `comparison|comparison:table:scale=none|from=table|scale=none`
- support: 591
- method: `llm_semantic_abstraction`
- description: Use when the question asks to identify a reporting period (e.g., a year) where a specific numeric metric is greater than, less than, or equal to another period's value or a given threshold, and the answer must be drawn directly from a table.
- evidence: Locate the table row or column that contains the metric label (e.g., 'revenue', 'amortisation', 'fair value per share').; Identify the column or row headers that represent reporting periods (e.g., years, quarters).; Extract the numeric values for each period under that metric, ensuring the correct unit (e.g., thousands, millions) is noted.; If a threshold is given in the question, compare each period's value against that threshold; otherwise, compare values across periods to find the maximum or minimum.
- roles: Metric label: the specific financial item being compared (e.g., revenue, net carrying amount).; Reporting period set: the list of time periods (e.g., years) from which the answer is selected.; Comparison condition: the relational operator (greater, less, equal) and optional threshold value.; Unit context: the scale or denomination of the numeric values (e.g., thousands, millions) that must be consistent across periods.
- scale: The scale is 'none', meaning no unit conversion is needed, but always verify that all values are in the same unit as stated in the table header.; If the table header indicates a unit (e.g., 'in thousands'), do not convert to absolute numbers unless the question explicitly asks for a different scale.; When comparing values, ignore any scale suffix in the question (e.g., 'thousands') if the table already uses that scale; otherwise, adjust the threshold accordingly.

### tatqa_strategy:13d6c9a655c6fcd2

- schema: `span_lookup|span_lookup:table-text:scale=thousand|from=table-text|scale=thousand`
- support: 574
- method: `llm_semantic_abstraction`
- description: Use this strategy when a question asks for a specific financial metric value at a given point in time or period, and the answer is a direct lookup from the table or text without any calculation or comparison.
- evidence: Locate the row or text segment that contains the exact metric label mentioned in the question.; Identify the column or sentence that corresponds to the specified reporting period (e.g., a date or year).; If the metric is not in the table, search the accompanying text for the same label and period.; Cross-check that the value is not a subtotal or total unless the question explicitly asks for it.
- roles: metric label: the specific financial item or account name (e.g., net income, finished products, accumulated other comprehensive income).; reporting period: the time point or interval (e.g., a fiscal year end, a quarter, a specific date) for which the value is requested.; context qualifier: any additional descriptors that narrow the metric (e.g., 'under capital lease', 'including accelerated stock-based compensation expense').
- scale: All values in this strategy are reported in thousands; do not convert or adjust the scale.; If the source shows a value in millions, it must be multiplied by a numeric value to match the thousand scale, but such cases are rare and should be flagged.; When extracting from text, ensure the number is not a percentage or a ratio unless the metric label explicitly indicates so.

### tatqa_strategy:d3818077874e80e6

- schema: `multi_span_lookup|multi_span_lookup:table-text:scale=none|from=table-text|scale=none`
- support: 558
- method: `llm_semantic_abstraction`
- description: Use when the question asks to enumerate or identify categories, components, segments, or variables that are listed in a table and may be further described or elaborated in the accompanying text.
- evidence: Locate the table row or column header that matches the broad category named in the question (e.g., components, segments, rates, variables).; Scan the table cells under that header for distinct labels or item names; these are the primary candidates for the answer.; If the question asks for 'respective' values or elaborations, cross-reference each label with the text paragraphs that mention the same label to extract the corresponding detail.; Check for any footnotes or sub-tables that break down the category further, as they may contain additional items not in the main table body.
- roles: Category header: the broad metric or account name that groups the items (e.g., 'components of inventories', 'pension discount rates', 'other current assets').; Item list: the individual labels or subcategories listed under the category header in the table.; Context qualifier: any additional condition in the question (e.g., 'for actuarial benefit obligation' vs. 'for benefit costs') that narrows which subset of items to report.; Text elaboration: the narrative text that provides extra description or values for the table items, used when the answer requires combining table and text.
- scale: This strategy typically does not require numeric scaling because the answer is a list of labels or names, not computed values.; If the question asks for 'respective' values, note that the values may be in different units (e.g., percentages vs. absolute amounts) depending on the item; do not convert or normalize them.; When extracting values from text, preserve the original units as stated (e.g., percent sign, currency) without applying any conversion.

### tatqa_strategy:83818188dec82af3

- schema: `arithmetic|arithmetic:difference|from=table|scale=million`
- support: 516
- method: `deterministic_arithmetic_template`
- description: Use when the question asks for an absolute difference or change between two values.
- evidence: Locate two comparable values for the same metric or requested pair.; Subtract in the direction implied by the question wording.
- roles: minuend_value; subtrahend_value; metric_or_item_label
- scale: Express the answer in million units when the task requires that scale.

### tatqa_strategy:f34fac3e1b266e36

- schema: `arithmetic|arithmetic:difference|from=table-text|scale=thousand`
- support: 486
- method: `deterministic_arithmetic_template`
- description: Use when the question asks for an absolute difference or change between two values.
- evidence: Locate two comparable values for the same metric or requested pair.; Subtract in the direction implied by the question wording.; Combine table values with nearby textual qualifiers when the evidence source is mixed.
- roles: minuend_value; subtrahend_value; metric_or_item_label
- scale: Express the answer in thousand units when the task requires that scale.

### tatqa_strategy:86258a5f531ea6dc

- schema: `span_lookup|span_lookup:table-text:scale=none|from=table-text|scale=none`
- support: 401
- method: `llm_semantic_abstraction`
- description: Use when the question asks for a single fact, value, or brief description that can be found directly in the table or its accompanying text, without requiring any arithmetic or cross-period comparison.
- evidence: Locate the table row or text passage that explicitly mentions the metric or topic named in the question.; If the question specifies a reporting period, match that period to the corresponding column or text segment.; If the question asks for a change or difference, look for a column or sentence that explicitly states the change, not compute it yourself.; For descriptive questions, scan the table title, headers, or nearby text for the explanation.
- roles: metric label: the specific financial or operational term being asked about (e.g., share repurchase, earnings per share, revenue).; reporting period: the time frame mentioned in the question, if any, used to select the correct row or column.; comparison anchor: the base period or item that the change is measured against, if the question implies a change.; item list: any enumerated items or categories that the question refers to, for locating the relevant row.
- scale: Report the value exactly as presented in the source, without converting units.; If the source uses a scale (e.g., thousands, millions), preserve that scale in the answer.; Do not apply any scaling or rounding unless the question explicitly requests it.

### tatqa_strategy:6a1aa75493114b69

- schema: `span_lookup|span_lookup:table:scale=none|from=table|scale=none`
- support: 382
- method: `llm_semantic_abstraction`
- description: Use when the question asks for a specific fact, amount, name, or attribute that is explicitly stated in a table, without requiring any calculation or comparison.
- evidence: Identify the table that contains the relevant metric or attribute label (e.g., 'stated capital', 'dividend', 'production volume', 'executive name').; Match the reporting period or date mentioned in the question to the corresponding row or column header in the table.; If the question asks for a person or entity, locate the row or column that lists names under the relevant role or title.; For currency or unit-related questions, find the table's stated base currency or unit in headers or footnotes.
- roles: metric label: the specific financial or operational term being asked about (e.g., 'stated capital', 'dividend', 'production volume').; reporting period: the date or time frame that identifies the correct row or column (e.g., a specific fiscal year-end or interim date).; attribute qualifier: any additional descriptor that narrows the lookup (e.g., 'final', 'comprised of', 'executive chairman').; entity or role: the organization or position name if the question asks for a person or entity.
- scale: The answer should be reported exactly as shown in the table, without converting units or applying any scaling factor.; If the table uses a specific unit (e.g., thousands, millions), the answer should reflect that unit unless the question explicitly asks for a different scale.; For currency amounts, confirm the base currency from the table header or notes; do not assume a standard currency.

### tatqa_strategy:5391a6ff8f15af23

- schema: `multi_span_lookup|multi_span_lookup:table:scale=none|from=table|scale=none`
- support: 368
- method: `llm_semantic_abstraction`
- description: Use when the question asks for a set of components, categories, or periods that are explicitly listed in a table, without requiring any arithmetic or cross-table comparison.
- evidence: Locate the table whose header or row labels match the subject of the question (e.g., actuarial assumptions, financial years, components).; Identify the column or row that contains the list of items; ensure the relevant rows/columns are within the same table.; If the question specifies multiple instances (e.g., 'in <num>, <num>, and <num>'), find the corresponding cells for each instance and extract them in the same order.
- roles: metric label: the category or component name being asked for (e.g., assumption type, year, component).; reporting period: the time frame or identifier that distinguishes multiple entries (e.g., specific years or periods).; item list: the set of values or labels to be extracted from the table.
- scale: No unit conversion or scaling is needed; values are taken as-is from the table.; If the table uses a common unit (e.g., years, percentages), preserve that unit in the answer.; Do not apply any rounding or formatting changes unless the table itself indicates them.

## Added Value Over Deterministic Labels

The LLM-generated lookup/count/comparison strategies add reusable semantic guidance that deterministic labels do not provide: where to look for evidence, whether to preserve a single span or multiple spans, what abstract roles to bind, how to treat mixed table/text evidence, and common scale/output risks. Arithmetic strategies intentionally add less prose because the deterministic formula family already captures most reusable procedure.

## Decision

The v0 memory is suitable for the next offline retrieval audit, with two constraints: keep this strategy set frozen for that audit, and treat leakage/QC checks as necessary but not sufficient before any execution experiment.

Decision: `READY FOR TAT-QA STRATEGY RETRIEVAL AUDIT`.
