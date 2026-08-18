# Grounded Abstraction Design: Literature Survey and Intervention Proposals

**Date**: 2025-01-20

**Context**: Strategy abstraction fails due to grounding loss (75.9% operator-only generation). Need middle ground between Case (grounded but specific) and Strategy (abstract but ungrounded).

---

## Problem Statement

**Forensic findings**:
- Case memory: Provides grounding but low generalization
- Strategy memory: Provides structure but loses operand binding
- Model failure: Cannot bind abstract roles (`<current_value>`) to concrete table cells (`table[2021][Revenue]`)

**Goal**: Design a representation that:
1. Preserves grounding information (which table, which row, which column)
2. Abstracts over specific values (2021 → any year, 145000 → any revenue)
3. Remains executable or easily instantiable
4. Requires minimal model capability overhead

---

## Literature Survey: Related Techniques

### 1. Case-Based Reasoning (CBR)

**Core idea**: Retrieve similar past cases, adapt to current problem

**Relevant techniques**:

#### 1.1 Structure Mapping Theory (Gentner, 1983)
- Analogical reasoning via structural alignment
- Separate relational structure from object attributes
- Map high-level relations while allowing object substitution

**Application to FinQA**:
```
Source case: subtract(revenue_2021, revenue_2020)
Target query: subtract(expenses_2022, expenses_2021)

Mapping:
  revenue → expenses
  2021 → 2022
  2020 → 2021
Preserved structure: subtract(later, earlier)
```

**Limitation**: Requires explicit structural representation and alignment algorithm.

#### 1.2 Case Adaptation Operators (Leake, 1996)
- Retrieve similar case
- Apply adaptation rules (substitution, scaling, deletion)
- Generate solution for new problem

**Application to FinQA**:
```
Retrieved: divide(operating_income, total_assets) → 0.025
Adaptation: Replace column names but preserve division structure
Generated: divide(net_income, total_equity)
```

**Limitation**: Requires hand-crafted or learned adaptation rules.

#### 1.3 Transformational Analogy (Carbonell, 1986)
- Store solution derivation traces, not just final solutions
- Replay derivation with current problem constraints

**Not directly applicable**: FinQA already provides step traces, issue is operand grounding not derivation structure.

### 2. Program Synthesis

**Core idea**: Generate programs from specifications or examples

**Relevant techniques**:

#### 2.1 Sketch-Based Synthesis (Solar-Lezama, 2008)
- User provides program sketch with holes: `multiply(??, ??)`
- Synthesizer fills holes with concrete values
- Uses constraint solving to find valid instantiation

**Application to FinQA**:
```
Sketch: subtract(??_1, ??_2), divide(#0, ??_2), multiply(#1, 100)
Constraints:
  ??_1: table column, year > ??_2.year
  ??_2: same table column as ??_1, earlier year
Solution: subtract(table[2021][Revenue], table[2020][Revenue]), ...
```

**Advantage**: Clear separation between structure and operands, constraint-guided instantiation.

**Limitation**: Requires constraint solver or model capable of constraint reasoning.

#### 2.2 Type-Directed Synthesis (Polikarpova et al., 2016)
- Use type system to constrain search space
- Types encode semantic properties (not just int/float)

**Application to FinQA**:
```
Types:
  CurrentYearRevenue <: TableCell[Year=2021, Column=Revenue]
  PriorYearRevenue <: TableCell[Year=2020, Column=Revenue]
  
Typed sketch:
  subtract(CurrentYearRevenue, PriorYearRevenue) → DeltaValue
  divide(DeltaValue, PriorYearRevenue) → GrowthRate
```

**Advantage**: Rich semantic types guide operand selection.

**Limitation**: Requires type inference and type-aware model.

#### 2.3 Programming-by-Example (Gulwani, 2011)
- FlashFill: Learn program from input-output examples
- Rank programs by simplicity and likelihood

**Not directly applicable**: FinQA already has example programs (Case memory), issue is generalization not induction.

### 3. Semantic Parsing

**Core idea**: Map natural language to executable logical forms

**Relevant techniques**:

#### 3.1 Grammar-Based Parsing with Lexicon (Zettlemoyer & Collins, 2005)
- Lexicon maps phrases to logical predicates
- Grammar composes predicates into full program

**Application to FinQA**:
```
Lexicon:
  "revenue in 2021" → table[Year=2021, Column=Revenue]
  "growth rate" → divide(subtract(current, prior), prior)

Parse: "What was the revenue growth rate from 2020 to 2021?"
  → divide(subtract(table[2021][Revenue], table[2020][Revenue]), table[2020][Revenue])
```

**Advantage**: Compositional, explicit phrase-to-predicate mapping.

**Limitation**: Requires lexicon construction and grammar engineering.

#### 3.2 Neural Semantic Parsing with Execution Guidance (Guu et al., 2017)
- Generate program candidates
- Execute on table and rank by consistency with question

**Limitation**: FinQA already uses neural generation, issue is operand selection not ranking.

#### 3.3 Schema-Linking for Text-to-SQL (Lei et al., 2020)
- Explicitly link question phrases to table schema elements
- Use linking to guide program generation

**Application to FinQA**:
```
Question: "What was the percentage increase in operating expenses?"
Schema links:
  "operating expenses" → Column[Name=Operating_Expenses]
  "increase" → Operation[Type=subtract, Temporal=year_over_year]
  "percentage" → Scale[Unit=percent, Transform=multiply_by_100]

Grounded program:
  subtract(table[2021][Operating_Expenses], table[2020][Operating_Expenses])
  divide(#0, table[2020][Operating_Expenses])
  multiply(#1, 100)
```

**Advantage**: Explicit grounding to schema, preserves table structure.

**This is the most promising direction.**

### 4. Neuro-Symbolic Reasoning

**Relevant techniques**:

#### 4.1 Neural Module Networks (Andreas et al., 2016)
- Parse question into module layout
- Modules are differentiable operations
- Compose modules to answer question

**Limitation**: Requires module library and layout prediction, heavyweight for FinQA.

#### 4.2 Latent Program Execution (Neelakantan et al., 2017)
- Learn to generate programs in latent space
- Execute programs to get answers

**Not applicable**: FinQA requires explicit programs for interpretability.

### 5. Educational Psychology (Computational Methods)

#### 5.1 Worked Examples with Fading (Renkl, 2014)
- Show complete example, gradually remove steps
- Learner fills in missing steps

**Application to FinQA**:
```
Complete example:
  subtract(145000, 132000) → 13000
  divide(13000, 132000) → 0.0985
  multiply(0.0985, 100) → 9.85

Faded sketch:
  subtract(??, ??)
  divide(#0, ??)
  multiply(#1, 100)

Learner (model) fills in operands from current query.
```

**Advantage**: Progressive abstraction, maintains structure while requiring operand instantiation.

**Limitation**: Unclear how to automatically determine optimal fading level.

#### 5.2 Example-Rule Interaction (VanLehn, 1996)
- Examples ground abstract rules
- Rules generalize specific examples
- Effective learning requires both

**Insight**: Confirms our finding that both Case and abstraction needed, but must be properly integrated.

---

## Proposed Interventions

### Proposal 1: Schema-Grounded Program Sketch (SGPS)

**Design**: Extend Strategy abstractions with explicit schema bindings

**Representation**:
```json
{
  "source_experience_id": "E001",
  "representation": "schema_sketch",
  
  "operation_sequence": [
    {"op": "subtract", "args": ["?current", "?prior"]},
    {"op": "divide", "args": ["#0", "?prior"]},
    {"op": "multiply", "args": ["#1", "?scale"]}
  ],
  
  "operand_constraints": {
    "?current": {
      "type": "table_cell",
      "column": "Revenue",
      "temporal_role": "current_year",
      "row_constraint": "year > ?prior.year"
    },
    "?prior": {
      "type": "table_cell",
      "column": "same_as(?current)",
      "temporal_role": "prior_year",
      "row_constraint": "year < ?current.year"
    },
    "?scale": {
      "type": "constant",
      "value": 100,
      "condition": "if output_unit == percentage"
    }
  },
  
  "reasoning_pattern": "year_over_year_growth_rate"
}
```

**Generation process**:
1. Model receives question + table + SGPS memory
2. Identifies columns matching constraints ("Revenue")
3. Identifies rows matching temporal constraints (2021 > 2020)
4. Instantiates sketch: `subtract(table[2021][Revenue], table[2020][Revenue])`
5. Continues for remaining operations

**Advantages**:
- Preserves table schema structure
- Explicit column/row constraints guide operand selection
- Maintains executability (once instantiated)
- Generalizes across specific values while grounding to table structure

**Implementation**:
- Construct SGPS from existing Case examples (automatic extraction)
- Format as structured prompt or JSON schema
- No model retraining required (prompt-based intervention)

**Expected improvement**:
- Reduces operator-only generation (preserves grounding cues)
- Maintains generalization benefits (abstracts over specific values)
- Target: 20-30% accuracy (between None 11.6% and Case 36.2%)

### Proposal 2: Column-Aware Case Memory (CACM)

**Design**: Enrich Case memory with explicit column annotations

**Representation**:
```json
{
  "source_experience_id": "E001",
  "representation": "annotated_case",
  
  "question": "What was the operating margin in 2021?",
  
  "program_annotated": [
    {
      "operation": "divide",
      "args": [
        {"value": "operating_income_2021", "column": "Operating_Income", "year": 2021},
        {"value": "revenue_2021", "column": "Revenue", "year": 2021}
      ],
      "result": 0.152
    }
  ],
  
  "program_raw": "divide(5200, 34200)",
  
  "schema_pattern": {
    "columns_used": ["Operating_Income", "Revenue"],
    "temporal_scope": "single_year",
    "operation_family": "ratio_calculation"
  }
}
```

**Generation process**:
1. Model receives question + table + annotated Case memory
2. Matches column names in current table to Case column annotations
3. Adapts program by substituting matched columns
4. Generates: `divide(table[2022][Operating_Income], table[2022][Revenue])`

**Advantages**:
- Minimal abstraction (still grounded examples)
- Explicit column annotations guide adaptation
- Preserves proven approach (Case memory works)
- Easy to construct automatically (column name extraction from table)

**Implementation**:
- Parse existing Case programs to extract operand-to-column mappings
- Annotate each operand with source column and constraints
- Present as structured case with metadata

**Expected improvement**:
- Maintains Case-level performance (~36%)
- Improves cross-domain generalization (column names as abstraction)
- Lower risk than full sketch-based approach

### Proposal 3: Hybrid Retrieve-Then-Adapt (RTA)

**Design**: Two-stage memory system combining Case and grounded sketch

**Stage 1: Retrieve**
- Find k=3 similar Case examples (current protocol)
- Find k=1 Schema-Grounded Sketch matching reasoning pattern

**Stage 2: Adapt**
- Show Case examples for concrete grounding
- Show SGPS for structural guidance
- Prompt: "Adapt the sketch using column names from current table, following the pattern in examples"

**Memory structure**:
```
### Similar Examples

Example 1: [Case with full program]
Example 2: [Case with full program]
Example 3: [Case with full program]

### Reasoning Pattern

Pattern: year_over_year_growth_rate
Operations: subtract(current, prior) → divide(#0, prior) → multiply(#1, 100)
Constraints:
  - current and prior must be same column
  - current year > prior year
  - multiply by 100 if output is percentage

### Your Task

Apply this pattern to the current question and table.
```

**Advantages**:
- Leverages proven Case utility (grounding)
- Adds structural guidance (sketch)
- Model can fall back to Case if sketch confusing
- Natural language constraints (easier than formal schema)

**Implementation**:
- Construct SGPS for top-k reasoning patterns in training data
- Store as natural language patterns (not JSON)
- Append to existing Case retrieval prompt

**Expected improvement**:
- Maintains Case baseline (~36%)
- Potential upside from structural guidance (+5-10pp)
- Robust to sketch quality issues (Case fallback)

---

## Comparison of Proposals

| Aspect | SGPS | CACM | RTA |
|--------|------|------|-----|
| **Grounding preservation** | Medium (schema constraints) | High (annotated values) | High (Case examples) |
| **Abstraction level** | High (formal constraints) | Low (column metadata) | Medium (NL patterns) |
| **Implementation complexity** | High (JSON schema extraction) | Low (column name parsing) | Medium (pattern mining) |
| **Model capability required** | High (constraint reasoning) | Low (column matching) | Medium (adaptation) |
| **Risk** | High (formal schema may confuse model) | Low (extends proven Case) | Medium (sketch may be ignored) |
| **Expected gain** | +10-20pp | +5-10pp | +10-15pp |

**Recommendation**: Start with **CACM** (low-risk), then test **RTA** (medium-risk), finally **SGPS** (high-risk).

---

## Implementation Roadmap

### Phase 1: Column-Aware Case Memory (CACM)

**Week 1-2: Automatic annotation**
1. Parse existing 90 Case memories
2. Extract column names from table context
3. Link program operands to table columns
4. Generate annotated Case representations

**Week 2-3: Prompt engineering**
1. Design annotated Case prompt format
2. Test on 10 queries (manual evaluation)
3. Refine annotation display

**Week 3-4: Experiment**
1. Run 224-query experiment with CACM memory
2. Compare: None, Case, CACM
3. Analyze: Does column annotation improve adaptation?

**Success criteria**: CACM ≥ Case (36.2%), with better cross-domain transfer

### Phase 2: Retrieve-Then-Adapt (RTA)

**Week 5-6: Pattern mining**
1. Cluster 90 Case examples by reasoning pattern
2. Extract top-10 patterns (YoY growth, ratio, aggregation, etc.)
3. Write natural language pattern descriptions
4. Map patterns to Case example subsets

**Week 6-7: Hybrid prompt design**
1. Combine Case + Pattern in single prompt
2. Test on 10 queries (manual evaluation)
3. A/B test: with vs without pattern guidance

**Week 7-8: Experiment**
1. Run 224-query experiment with RTA memory
2. Compare: None, Case, CACM, RTA
3. Analyze: Does pattern guidance help beyond Case?

**Success criteria**: RTA > Case (36.2%), ideally 40-45%

### Phase 3: Schema-Grounded Sketch (SGPS)

**Week 9-10: Schema extraction**
1. Build schema parser for FinQA tables
2. Extract column types, temporal patterns, constraints
3. Generate formal constraint specifications
4. Convert Case examples to SGPS format

**Week 10-11: Prompt engineering**
1. Design SGPS JSON schema prompt
2. Test if model can instantiate sketches
3. Refine constraint language for model comprehension

**Week 11-12: Experiment**
1. Run 224-query experiment with SGPS memory
2. Compare: None, Case, CACM, RTA, SGPS
3. Analyze: Does formal schema help or confuse?

**Success criteria**: SGPS > CACM, minimal operator-only generation

---

## Validation Plan

### Metrics

**Primary (program-level)**:
- Accuracy: % programs correct
- Coverage: % programs executable
- Operator-only rate: % responses without operands

**Secondary (mechanism)**:
- Column match accuracy: % operands from correct columns
- Temporal constraint satisfaction: % operations respect year ordering
- Scale preservation: % percentage operations include ×100

**Comparison**:
- None (baseline): 11.6%
- Case (current best): 36.2%
- CACM target: ≥36%
- RTA target: 40-45%
- SGPS target: 35-40%

### Diagnostic Analysis

**For each intervention**:
1. Sample 20 responses (10 success, 10 failure)
2. Manual inspection: Why did it work/fail?
3. Classify failure modes:
   - Column mismatch (wrong table column selected)
   - Temporal error (year ordering violated)
   - Scale error (missing ×100 for percentage)
   - Operation error (wrong operation sequence)
   - Operator-only (grounding failed completely)

**Success patterns**:
- When does CACM adaptation work?
- When does RTA pattern guidance help?
- When does SGPS constraint reasoning succeed?

### Ablation Studies

**For RTA**:
- Case only
- Pattern only
- Case + Pattern (full RTA)

**For SGPS**:
- With column constraints
- With temporal constraints
- With scale constraints
- With all constraints (full SGPS)

---

## Theoretical Contribution

### Beyond Empirical Observation

**Current state**: "Case helps, Strategy fails" (empirical finding)

**With grounded abstractions**:

**If CACM succeeds**:
- **Claim**: "Column-level grounding is the minimal abstraction that preserves utility"
- **Mechanism**: Concrete values → column names (preserves table structure, abstracts specific numbers)
- **Contribution**: Identifies optimal abstraction granularity for table reasoning

**If RTA succeeds**:
- **Claim**: "Hybrid memory with grounding anchors + structural guidance outperforms single-level representations"
- **Mechanism**: Case provides grounding scaffolding, Pattern provides reasoning template
- **Contribution**: Design principle for multi-level memory systems

**If SGPS succeeds**:
- **Claim**: "Schema-aware abstractions enable grounded generalization in structured reasoning"
- **Mechanism**: Formal constraints guide operand selection while preserving executability
- **Contribution**: Framework for abstraction design in structured domains

### Positioning in Literature

**Case-Based Reasoning**: Concrete intervention in modern neural setting, shows CBR adaptation principles applicable to LLM reasoning

**Program Synthesis**: Demonstrates sketch-based approach can work with neural generation, bridges symbolic and neural methods

**Semantic Parsing**: Validates schema-linking insight for financial reasoning, extends text-to-SQL techniques to numerical reasoning

**Neuro-Symbolic**: Practical lightweight integration (no module networks, just structured prompts)

---

## Risks and Mitigation

### Risk 1: Column names are ambiguous

**Example**: "Revenue" vs "Total_Revenue" vs "Operating_Revenue"

**Mitigation**:
- Use fuzzy column matching
- Provide table schema in prompt
- Fall back to Case examples if column matching fails

### Risk 2: Formal constraints confuse model

**Example**: Model cannot interpret JSON schema constraints

**Mitigation**:
- Start with natural language constraints (RTA)
- Only use SGPS if RTA shows model can reason about patterns
- Provide constraint examples in prompt

### Risk 3: Intervention cost is too high

**Example**: Column annotation requires expensive parsing

**Mitigation**:
- Use regex + heuristic column extraction (cheap)
- Manual annotation for pattern templates (one-time cost)
- Reuse existing Case examples (no new retrieval)

### Risk 4: Model ignores new memory structure

**Example**: RTA pattern guidance ignored, model just uses Case

**Mitigation**:
- Measure attention: Do responses cite pattern?
- A/B test: Verify pattern presence changes behavior
- If ignored, abandon intervention and stick with Case

---

## Summary

**Problem**: Strategy abstractions lose grounding, causing 75.9% operator-only generation

**Solution space**: Grounded abstractions that preserve table schema while generalizing over values

**Proposed interventions**:
1. **CACM** (low-risk): Annotate Case examples with column names
2. **RTA** (medium-risk): Combine Case + natural language reasoning patterns
3. **SGPS** (high-risk): Formal schema constraints with typed operand slots

**Recommended path**: CACM → RTA → SGPS (increasing risk/reward)

**Theoretical contribution**: Identify optimal abstraction granularity for structured reasoning, demonstrate grounded abstraction design principles

**Timeline**: 12 weeks for all three phases

**Next immediate action**: Implement CACM column annotation pipeline

---

**Document Generated**: 2025-01-20  
**Status**: Design complete, ready for implementation  
**Next Step**: Build CACM automatic annotation system
