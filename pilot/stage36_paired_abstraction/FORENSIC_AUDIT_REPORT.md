# Strategy Failure Forensic Audit Report

**Date**: 2025-01-20

**Context**: Stage 37 expanded validation showed Strategy arm collapsed from +13.3pp (pilot) to -5.4pp (expanded)

---

## Executive Summary

### Root Cause Identified

**Strategy memory causes the model to generate OPERATOR-ONLY programs without operands.**

170/224 (75.9%) Strategy responses contain bare operator sequences like:
```
PROGRAM: subtract, divide, multiply
PROGRAM: table_max, divide
PROGRAM: add, add
```

Instead of executable programs with operands:
```
PROGRAM: subtract(1505, 2504), divide(#0, 2504), multiply(#1, 100)
```

**This is NOT an execution failure — it's INCOMPLETE GENERATION.**

The model outputs the abstract reasoning structure from Strategy memory but fails to instantiate it with concrete operands from the current query.

---

## Detailed Findings

### Finding 1: Strategy Generation Funnel

```
Total queries:               224 (100.0%)
Has PROGRAM: line:           220 (98.2%)  ← Model generates PROGRAM line
Parsed successfully:         220 (98.2%)  ← Raw text extracted
Executed successfully:        29 (12.9%)  ← Catastrophic drop
Program correct:              14 (6.2%)
```

**Comparison with None baseline**:
```
Metric                      None        Strategy    Δ
Execution success rate      26.3%       12.9%       -13.4pp
Program correct rate        11.6%       6.2%        -5.4pp
```

**Strategy execution rate is LOWER than baseline with no memory.**

### Finding 2: Parse_Fail Does Not Mean Parsing Failed

**All 170 parse_fail cases have**:
- ✓ `raw_program` field (extracted from response)
- ✓ `normalized_program` field (same as raw)
- ✗ Executable program (no operands, only operators)

**What "parse_fail" actually means**:
- FinQA executor's `parse_program_re()` expects: `operator(arg1, arg2)`
- Strategy generates: `operator, operator, operator`
- Executor rejects: "expected '(' after op"

**This is operator-only generation, not parsing failure.**

### Finding 3: Strategy Response Pattern

**Sample raw responses**:

```
Query: RE/2015/page_33.pdf-2 (Gold: 0.03558)
PROGRAM: subtract, divide, multiply
ANSWER: 3.56
```

```
Query: GS/2017/page_143.pdf-1 (Gold: -0.39896)
PROGRAM: subtract, divide, multiply
ANSWER: -39.9
```

```
Query: PM/2017/page_99.pdf-3 (Gold: 2.0)
PROGRAM: subtract, table_max
ANSWER: 2
```

**Pattern**: Model generates:
1. Abstract operator sequence (from Strategy memory)
2. Final answer (computed somehow, often wrong)
3. NO concrete program with operands

**Mechanism**: Strategy memory provides abstract formula templates like:
```
Operation sequence: subtract → divide → multiply
Operand roles: <current_value>, <previous_value>, <denominator>
```

But the model fails to **bind** these abstract roles to concrete table values.

### Finding 4: Execution Failure (21 cases, 9.4%)

**Pattern**: Programs parse but fail execution

**90.5% are table operation failures**:
```
PROGRAM: table_max, table_min, table_sum, table_average, add, subtract, multiply, divide, exp, greater
```

**Root cause**: Strategy abstractions suggest table operations (aggregate functions) but:
- Don't specify which table column
- Don't provide table data structure
- Executor receives no table context → execution fails

**One malformed syntax case** (STZ/2006/page_68.pdf-2):
- 1000+ "subtract" operators repeated
- Model generation completely failed (repetition loop)

### Finding 5: Strategy Rescues (9 cases, 4.0%)

**When Strategy helps**:

```
JPM/2014/page_65.pdf-5
  None: parse_fail
  Strategy: success → "no" (correct)
  
MO/2012/page_44.pdf-2
  None: exec_fail
  Strategy: success → 1.66387 (correct)
  
CAG/2008/page_75.pdf-2
  None: success → 61.05 (wrong, ×100 error)
  Strategy: success → 0.61046 (correct)
```

**Pattern**: Strategy rescues are rare (4%) but genuine
- Scale/percentage errors corrected
- Parse failures rescued with valid programs
- Some queries benefit from abstract reasoning structure

**Hypothesis**: Rescues occur when:
- Query has clear reasoning structure that matches Strategy template
- Grounding demands are low (few similar values to disambiguate)
- Model successfully binds abstract roles to concrete operands

### Finding 6: Strategy Harms (21 cases, 9.4%)

**When Strategy hurts**:

```
BLL/2007/page_47.pdf-4
  None: success → 102.5 (correct)
  Strategy: parse_fail
  
TFX/2015/page_70.pdf-3
  None: success → 386797189.66 (correct)
  Strategy: parse_fail
```

**Pattern**: None baseline succeeds, Strategy generates operator-only program

**10 harm cases are invariant-correct queries** (None succeeds on these)
- Strategy memory causes model to generate incomplete programs
- Loses working baseline behavior

### Finding 7: Case vs Strategy Disagreement (73 cases, 32.6%)

```
Case correct, Strategy wrong:  70 (31.3%)
Strategy correct, Case wrong:   3 (1.3%)
```

**Overwhelming Case advantage**

**Case wins pattern**:
- Case generates valid executable programs
- Strategy generates operator-only sequences
- Case provides concrete grounding, Strategy loses it

**Strategy wins (3 rare cases)**:
```
MO/2012/page_44.pdf-2: Case no_program, Strategy success
STT/2009/page_73.pdf-2: Case success (wrong), Strategy success (correct)
ETR/2013/page_118.pdf-3: Case no_program, Strategy success
```

Small sample (3/224 = 1.3%), suggests Strategy occasionally captures reasoning structure Case misses.

---

## Mechanism Analysis

### Why Does Strategy Fail?

**Strategy memory provides**:
```json
{
  "operation_sequence": "subtract → divide → multiply",
  "operand_roles": ["current_value", "previous_value", "denominator"],
  "formula_template": "(current - previous) / previous × 100"
}
```

**What the model needs to do**:
1. Match abstract roles to concrete table values
2. Identify "current_value" = row 2021, column "Revenue"
3. Identify "previous_value" = row 2020, column "Revenue"
4. Generate: `subtract(table[2021][Revenue], table[2020][Revenue])`

**What the model actually does**:
1. Copies abstract operator sequence: "subtract, divide, multiply"
2. Computes final answer somehow (often wrong)
3. Never instantiates operands

**Root cause**: **Grounding failure**

Strategy abstractions are **ungrounded templates** — they capture reasoning structure but lose the concrete binding information that Case examples provide.

### Why Does Case Succeed?

**Case memory provides**:
```
Question: What was the revenue growth rate from 2020 to 2021?
Program: subtract(145000, 132000), divide(#0, 132000), multiply(#1, 100)
Answer: 9.85%
```

**What the model does**:
1. Recognizes similar question pattern
2. Directly adapts concrete program structure
3. Replaces specific values (145000 → current query's revenue)
4. Preserves operand grounding and execution structure

**Case provides grounding scaffolding** — concrete examples show:
- Which table values to select
- How to reference them in program syntax
- Correct scale/unit handling

### Abstraction vs Grounding Trade-off

**Hypothesis confirmed**:

```
Case:     High grounding, Low abstraction  → Works (36.2% accuracy)
Strategy: Low grounding, High abstraction  → Fails (6.2% accuracy)
Paired:   Inherits Case grounding          → Works (34.4% accuracy)
```

**FinQA is grounding-dominated**:
- Correct operand selection critical
- Table structure understanding critical
- Scale/unit preservation critical
- Abstract reasoning structure alone insufficient

**Analogy**:
- Strategy is like giving someone a recipe without ingredients
- Case is like showing a completed dish with all ingredients listed

---

## Failure Taxonomy

### 1. Operator-Only Generation (170 cases, 75.9%)

**Pattern**: `subtract, divide, multiply` instead of `subtract(a, b), divide(#0, c)`

**Cause**: Model copies abstract structure but fails operand instantiation

**Severity**: Critical — prevents program execution entirely

### 2. Table Operation Without Context (19 cases, 8.5%)

**Pattern**: `table_max, table_sum, divide` without column specification

**Cause**: Strategy suggests aggregate operations but loses table schema

**Severity**: High — parsed but unexecutable

### 3. Scale/Unit Errors (observed in answers, not programs)

**Pattern**: Answer shows ×100 errors (3.56 instead of 0.03558)

**Cause**: Strategy abstractions don't preserve scale constraints

**Severity**: Medium — program may execute but gets wrong result

### 4. Generation Repetition Loop (1 case, 0.4%)

**Pattern**: 1000+ repeated operators

**Cause**: Model generation completely failed (rare pathology)

**Severity**: Critical but rare

### 5. Valid But Wrong (15 cases, 6.7%)

**Pattern**: Program executes but produces wrong answer

**Cause**: Operand selection error or wrong operation sequence

**Severity**: Medium — at least generates executable program

---

## Comparison with Pilot

### Pilot (30 queries)

- Strategy: 10/30 correct (33.3%)
- Parse coverage: 23/30 (76.7%)
- Execution coverage: 20/30 (66.7%)
- Operator-only generation: ~23% (estimated)

### Expanded (224 queries)

- Strategy: 14/224 correct (6.2%)
- Parse coverage: 220/224 (98.2%)
- Execution coverage: 29/224 (12.9%)
- Operator-only generation: 75.9%

**Why did pilot overestimate Strategy utility?**

1. **Sample selection bias**: Pilot queries curated for "reasoning challenge"
   - May have favored structure-heavy, grounding-light queries
   - Strategy abstractions more useful on complex multi-step reasoning

2. **Small sample noise**: 10/30 vs 14/224
   - Pilot: 33.3% ± 8.6% (binomial SE)
   - Expanded: 6.2% ± 1.6%
   - Pilot CI does not overlap expanded estimate

3. **Operator-only generation rate**:
   - Pilot: ~23% (7/30 parse-fail)
   - Expanded: 75.9% (170/224 parse-fail)
   - Strategy abstractions trigger incomplete generation much more on typical queries

**Conclusion**: Pilot sample was **not representative** of broader FinQA distribution.

---

## Key Insights

### 1. Abstraction Loses Grounding

Strategy memory strips away the concrete binding information that Case memory preserves.

**Case**: "subtract(145000, 132000)" → shows exactly which values from which table cells  
**Strategy**: "subtract(<current>, <previous>)" → abstract roles, model can't ground

### 2. FinQA Requires Grounding-Heavy Reasoning

- Operand selection: Which of 5 similar numbers is "current revenue"?
- Table navigation: Which row, which column?
- Scale/unit: Is this a percentage (divide by 100) or ratio (keep decimal)?

Abstract reasoning structure alone is insufficient.

### 3. Model Cannot Reliably Bind Abstract Roles

The model fails to:
- Map `<current_value>` → `table[2021][Revenue]`
- Map `<previous_value>` → `table[2020][Revenue]`
- Generate executable syntax from abstract templates

**This is a capability boundary** — current models struggle with symbolic grounding tasks.

### 4. Paired Works Because It Inherits Case

Paired memory contains both Case and Strategy, but:
- Paired accuracy (34.4%) ≈ Case accuracy (36.2%)
- Paired rescues (27.7%) ≈ Case rescues (28.1%)

**Interpretation**: Model primarily uses Case examples, ignores or fails to utilize Strategy abstractions.

### 5. Strategy Utility is Query-Dependent (Hypothesis)

9 Strategy rescues (4.0%) suggest occasional utility:
- Complex multi-step reasoning where structure matters
- Low grounding demands (few ambiguous operands)
- Clear pattern match to Strategy template

**But**: 75.9% failure rate overwhelms rare benefits.

---

## Implications for Research Direction

### Original Hypothesis: REFUTED

> "When does experience abstraction help?"

**Finding**: Higher abstraction (Strategy) does NOT help at scale in FinQA.

**Refined understanding**: Abstraction-grounding trade-off is critical. FinQA sits firmly on the grounding-heavy side.

### Revised Research Question

**Option A**: "Why does concrete memory help, and how can we preserve grounding while gaining generality?"

**Option B**: "What is the optimal abstraction level for different reasoning task types?"

**Option C**: "Can we build grounded abstractions that preserve binding information?"

### What We Can Publish Now

**Strong claims**:
- ✓ Case-level memory helps substantially (+24.6pp, stable)
- ✓ Grounding information is critical for FinQA reasoning
- ✓ Abstract templates without operand grounding fail catastrophically
- ✓ Program-level evaluation reveals mechanism invisible to answer-level

**Weak/uncertain claims**:
- ? Strategy helps on complex/structure-heavy queries (only 9 rescues, 4%)
- ? Paired shows complementarity (appears to just inherit Case)
- ? Abstraction hierarchy exists (only tested two levels, higher failed)

---

## Recommended Next Steps

### Immediate: Grounded Abstraction Design

**Goal**: Create a middle ground between Case and Strategy that preserves grounding.

**Candidate: Program Sketch Memory**

Instead of full abstraction:
```
Strategy: "subtract(<current>, <previous>), divide(#0, <previous>)"
```

Use grounded sketch:
```
Sketch: "subtract(table[year=2021][col=Revenue], table[year=2020][col=Revenue]), divide(#0, #1)"
Constraints: {
  "scale": "decimal_ratio",
  "operand_count": 2,
  "table_columns": ["Revenue"],
  "temporal_pattern": "year_over_year"
}
```

**Preserves**:
- Table structure (year, column)
- Operand roles with table schema binding
- Scale/unit constraints
- Execution syntax structure

**Abstracts**:
- Specific values (2021 vs 2022)
- Exact numbers
- Company names

### Short-term: Query Stratification

**Test**: Does Strategy help on complex queries but harm on simple ones?

**Method**:
- Segment 224 queries by operation complexity
  - Simple: 1-step, single table lookup
  - Complex: 3+ steps, multi-row aggregation
- Compare Case vs Strategy within each segment

**Hypothesis**: Strategy failure concentrated in simple queries, rescues concentrated in complex queries.

### Medium-term: Case-Only Ablation

**Test**: Is Paired just Case, or does Strategy contribute?

**Method**: Run Case-only arm (no Strategy component) on same 224 queries

**Expected outcome**: Case-only ≈ Paired (validates that Strategy is ignored)

---

## Scientific Boundaries

### FACTS

- 170/224 (75.9%) Strategy responses are operator-only sequences
- 19/21 (90.5%) Strategy exec-fail cases are table operations without context
- 70/73 (95.9%) Case-Strategy disagreements favor Case
- 9/224 (4.0%) Strategy rescues exist but are rare
- Model generates PROGRAM: line but fails operand instantiation

### SUPPORTED INTERPRETATIONS

- Strategy abstractions cause grounding failure
- Model cannot reliably bind abstract roles to concrete table values
- FinQA is grounding-dominated (operand selection critical)
- Case memory provides grounding scaffolding that Strategy lacks
- Abstraction-grounding trade-off is real and consequential
- Pilot sample was not representative (selection bias + small n)

### OPEN QUESTIONS

- Can grounded abstractions (sketches with schema) work?
- Is Strategy useful on complex-query subset?
- What model capabilities are required for abstract role binding?
- Would intermediate abstraction levels (between Case and Strategy) help?
- Can retrieval quality predict when Strategy helps vs harms?

---

**Report Generated**: 2025-01-20  
**Status**: Forensic audit complete, mechanism identified  
**Next Action**: Design grounded abstraction intervention
