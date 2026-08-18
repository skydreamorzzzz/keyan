# Stage 37 Summary: Expanded Validation & Path Forward

**Date**: 2025-01-20

---

## What Was Completed

### 1. Expanded Stability Validation (Stage 37)

**Experiment execution**: ✓ Complete
- 224 queries × 4 arms = 896 API calls
- DeepSeek-V4-Flash, temperature=0.0, k=3 retrieval
- Shared-source memory control maintained
- Single continuous run with incremental checkpointing

**Results**:
```
Program-level accuracy:
  None:     26/224 (11.6%)  [baseline]
  Case:     81/224 (36.2%)  [+24.6pp, stable from pilot]
  Strategy: 14/224 ( 6.2%)  [-5.4pp, COLLAPSED from pilot +13.3pp]
  Paired:   77/224 (34.4%)  [+22.8pp, stable from pilot]
```

**Key finding**: Case utility confirmed stable at scale. Strategy effect completely reversed (pilot +13.3pp → expanded -5.4pp).

### 2. Strategy Failure Forensic Audit

**Root cause identified**: Strategy memory causes operator-only generation

**170/224 (75.9%) Strategy responses**:
```
PROGRAM: subtract, divide, multiply
PROGRAM: table_max, divide
PROGRAM: add, add
```

Instead of executable programs:
```
PROGRAM: subtract(1505, 2504), divide(#0, 2504), multiply(#1, 100)
```

**Mechanism**: Model outputs abstract reasoning structure from Strategy memory but **fails to instantiate operands** from current query table.

**Grounding failure**: Strategy abstractions strip away concrete binding information that Case examples preserve. Model cannot map abstract roles (`<current_value>`) to concrete table cells (`table[2021][Revenue]`).

### 3. Grounded Abstraction Design

**Problem framing**: Need middle ground between:
- Case: High grounding, low abstraction → works (36.2%)
- Strategy: High abstraction, low grounding → fails (6.2%)

**Literature surveyed**:
1. Case-Based Reasoning (structure mapping, case adaptation)
2. Program Synthesis (sketch-based, type-directed)
3. Semantic Parsing (schema-linking, grounding)
4. Neuro-Symbolic (neural modules, latent programs)
5. Educational methods (worked examples, fading)

**Three interventions designed**:

**CACM (Column-Aware Case Memory)** - Low risk
- Annotate Case examples with explicit column names
- Model adapts by matching columns in current table
- Expected: ≥36% (maintains Case utility, improves adaptation)

**RTA (Retrieve-Then-Adapt)** - Medium risk
- Combine Case examples + natural language reasoning patterns
- Case provides grounding, pattern provides structure
- Expected: 40-45% (Case baseline + pattern guidance)

**SGPS (Schema-Grounded Program Sketch)** - High risk
- Formal sketches with typed slots and schema constraints
- Preserves table structure while abstracting values
- Expected: 35-40% (if model can reason about constraints)

---

## Scientific Findings

### Confirmed

✓ **Case memory has genuine reasoning utility at scale**
- Effect stable: pilot +26.7pp → expanded +24.6pp
- 63/224 rescues (28.1%), substantial and consistent
- Mechanism: Concrete examples provide operand grounding

✓ **Grounding information is critical for FinQA reasoning**
- Operand selection from similar table values
- Table structure navigation (row/column)
- Scale/unit preservation (percentage vs decimal)

✓ **Abstract memory alone is insufficient**
- Strategy execution coverage (12.9%) < None baseline (26.3%)
- 75.9% operator-only generation (incomplete programs)
- Model cannot reliably bind abstract roles to concrete operands

✓ **Abstraction is not monotonically beneficial**
- Higher abstraction ≠ better performance
- Abstraction-grounding trade-off is real
- FinQA sits on grounding-heavy side of spectrum

### Refuted

✗ **Strategy abstraction helps at scale**
- Pilot +13.3pp was not representative (small sample bias)
- Expanded -5.4pp shows net harm
- Only 9/224 rescues (4.0%), overwhelmed by 170 failures

✗ **Abstraction hierarchy is monotonic**
- Strategy (high abstraction) performs worse than None (no memory)
- More abstract ≠ more useful

✗ **Paired shows true complementarity**
- Paired (34.4%) ≈ Case (36.2%)
- Paired likely inherits Case utility, ignores Strategy
- No evidence of Case + Strategy synergy

### Open Questions

? **When does Strategy help?**
- 9 genuine rescues exist (4.0%)
- Hypothesis: Complex multi-step reasoning where structure matters
- Requires query stratification analysis

? **Can grounded abstractions work?**
- CACM/RTA/SGPS interventions untested
- If successful, validates "grounding-preserving abstraction" principle

? **What is optimal abstraction level?**
- Case = concrete examples
- CACM = column-level abstraction
- SGPS = schema-level abstraction
- Strategy = full abstraction (loses grounding)
- Need systematic comparison across levels

---

## Research Status

### Original Hypothesis

> "When Does Experience Abstraction Help?"

**Status**: REFUTED at original framing

Higher abstraction (Strategy) does not help in FinQA reasoning at scale.

### Refined Research Question

> "What abstraction level preserves grounding while enabling generalization?"

**Status**: OPEN, with clear path forward (CACM → RTA → SGPS)

### Publication Readiness

**Current state**: NOT READY (mechanism understood, solution untested)

**Can publish**:
- Case memory utility (stable +24.6pp)
- Grounding-abstraction trade-off (empirical + mechanistic evidence)
- Operator-only generation failure mode (new finding)
- Program-level vs answer-level evaluation (methodological insight)

**Cannot yet publish**:
- "When abstraction helps" (Strategy collapsed)
- "Optimal abstraction level" (need CACM/RTA/SGPS results)
- "Design principles for abstraction" (need intervention validation)

**Recommended timeline**: 8-12 weeks for CACM+RTA experiments, then reassess

---

## Next Actions

### Immediate (Week 1-2): CACM Implementation

**Goal**: Annotate existing 90 Case examples with column names

**Tasks**:
1. Build column extraction pipeline
   - Parse table context from Case experiences
   - Link program operands to table columns
   - Generate annotated Case JSON

2. Test annotation quality
   - Manual inspection: 10 annotated cases
   - Verify column-operand mappings correct
   - Refine extraction heuristics

3. Design CACM prompt format
   - Show annotated examples in prompt
   - Guide model to adapt using column names
   - A/B test: with vs without annotations

**Deliverable**: 90 annotated Case memories + CACM prompt template

### Short-term (Week 3-4): CACM Experiment

**Goal**: Validate column-level grounding preserves utility

**Tasks**:
1. Run 224-query experiment: None, Case, CACM
2. Program-level audit with same pipeline
3. Compare:
   - Accuracy: CACM vs Case
   - Coverage: Operator-only rate
   - Adaptation: Cross-domain column matching

**Success criteria**: CACM ≥ 36% (maintains Case), with evidence of improved adaptation

### Medium-term (Week 5-8): RTA Design & Experiment

**Goal**: Test if pattern guidance improves over Case alone

**Tasks**:
1. Mine top-10 reasoning patterns from Case examples
2. Write natural language pattern descriptions
3. Design hybrid prompt: Case + Pattern
4. Run 224-query experiment: None, Case, CACM, RTA
5. Analyze: Does pattern guidance add value?

**Success criteria**: RTA > Case (target 40-45%)

### Long-term (Week 9-12): Publication

**After CACM+RTA validation**:

**If CACM succeeds**:
- Frame: "Column-level grounding is optimal abstraction for table reasoning"
- Contribution: Identifies abstraction granularity principle

**If RTA succeeds**:
- Frame: "Hybrid grounding + structure outperforms single-level memory"
- Contribution: Multi-level memory design for structured reasoning

**If both fail**:
- Frame: "Case-level concrete examples are necessary for table reasoning"
- Contribution: Identifies grounding boundary for current models

---

## Deliverables Generated

### Stage 37 Outputs

**Experimental data**:
- `results_none_expanded.json` (224 responses)
- `results_case_expanded.json` (224 responses)
- `results_strategy_expanded.json` (224 responses)
- `results_paired_expanded.json` (224 responses)
- `expanded_sample_queries.json` (224 queries, 30 pilot + 194 new)

**Audit results**:
- `expanded_audit_canonical.json` (896 records, program-level)
- `expanded_audit_summary.json` (per-arm statistics)
- `expanded_audit_transitions.json` (rescue/harm patterns)

**Analysis reports**:
- `STAGE37_EXPANDED_STABILITY_VERDICT.md` (stability comparison, mixed verdict)
- `FORENSIC_AUDIT_REPORT.md` (root cause analysis, operator-only generation)
- `GROUNDED_ABSTRACTION_DESIGN.md` (intervention proposals, literature survey)
- `forensic_audit.py` (analysis script)

**Prior reports** (for reference):
- `STAGE36_REPAIRED_PILOT_VERDICT.md` (30-query pilot, GO decision)
- `program_level_audit.py` (canonical audit script)

---

## Key Insights for User

### 1. Strategy collapsed because it's ungrounded

Not an evaluation artifact, not a model bug, not a retrieval issue. **Fundamental abstraction-grounding trade-off**.

Strategy provides reasoning structure but loses the concrete binding information models need to select operands from tables.

### 2. Case works because it provides grounding scaffolding

Concrete examples show:
- Which table values to use
- How to reference them in programs
- Correct scale/unit handling

This is why Case (36.2%) >> Strategy (6.2%).

### 3. Pilot was not representative

30-query pilot overestimated Strategy utility due to:
- Small sample noise (33.3% ± 8.6%)
- Selection bias (curated "reasoning challenge" queries)
- Lower operator-only generation rate (23% vs 75.9%)

Expanded 224-query sample reveals true effect.

### 4. Solution path is clear

Don't abandon abstraction entirely. Build **grounded abstractions**:
- CACM: Column-level (minimal abstraction, maximal grounding)
- RTA: Pattern-level (moderate abstraction, anchored by Case)
- SGPS: Schema-level (high abstraction, constrained by structure)

Test systematically to find optimal abstraction granularity.

### 5. This is publishable work

**Current contribution**:
- Empirical: Case memory helps, Strategy doesn't
- Mechanistic: Grounding failure causes operator-only generation
- Methodological: Program-level evaluation essential

**With interventions**:
- Theoretical: Optimal abstraction level for structured reasoning
- Practical: Design principles for memory systems in table reasoning
- Generalizable: Grounding-abstraction trade-off applies beyond FinQA

---

## Status Summary

**Experiment complete**: ✓ 896 API calls, all data collected and audited

**Mechanism understood**: ✓ Strategy causes grounding failure (operator-only generation)

**Solution designed**: ✓ Three grounded abstraction interventions (CACM, RTA, SGPS)

**Next step**: Implement CACM annotation pipeline (low-risk, 2 weeks)

**Publication timeline**: 8-12 weeks (after CACM+RTA validation)

---

**Report Generated**: 2025-01-20  
**Status**: Stage 37 complete, moving to grounded abstraction implementation  
**Next Action**: Build CACM column annotation system
