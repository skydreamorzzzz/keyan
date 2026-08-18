# FinQA Memory Construction Audit: Paired Abstraction Assessment

**Date**: 2026-08-18  
**Context**: User requested audit to determine if existing FinQA Case/Strategy memories support controlled abstraction study where Case(E) and Strategy(E) derive from same source experience E.

---

## Executive Summary

**FINDING: Current FinQA memory construction does NOT support paired abstraction study.**

Current Strategy Memory aggregates multiple Cases per strategy via struct clustering + LLM abstraction. Case(i) and Strategy(j) do NOT trace to same source experience E, violating the controlled paired design requirement.

**Implication**: Existing FinQA Stage 1-2 four-arm results remain valid as **exploratory evidence** of memory effects in general, but **cannot support causal claims** about "abstraction operator" effects isolated from confounding factors.

---

## 1. Provenance Assessment

### Case Memory Construction
- **Source**: train.json (6,251 samples)
- **Method**: Direct copy, no LLM rewriting
- **Mapping**: 1 train sample → 1 Case Memory entry
- **Fields**: case_id, report, company, question, problem_kind, n_steps, struct, gold_facts, program, steps, exe_ans, answer, retrieval_text
- **Code**: `pilot/build_case_memory.py`

**Conclusion**: Case Memory preserves concrete experiences 1:1 from source data.

### Strategy Memory Construction
- **Source**: train.json top-25 struct clusters (~96% coverage)
- **Method**: Struct clustering → sample 6 examples per struct → LLM abstraction prompt "group these examples into 1-3 strategies"
- **Mapping**: Multiple train samples (same struct) → 1-3 Strategy entries
- **Fields**: strategy_id, name, problem_type, source_struct, example_ids (3-6 case_ids), template, formula, operand_roles, retrieval_text
- **Code**: `pilot/build_strategy_memory.py`

**Key evidence from code**:
```python
# Line 82-84 in build_strategy_memory.py
user = ("Here are the solved examples:\n\n" + 
        "\n\n".join(fmt_example(e) for e in exs) +
        "\n\nNow output the JSON array of strategies (group the examples into 1-3 strategies).")
```

**Conclusion**: Strategy Memory aggregates multiple Cases per strategy. NOT 1:1 paired abstraction.

---

## 2. Traceability Analysis

**Quantitative evidence**:
- Total Cases: 6,251
- Total Strategies: 44
- Cases referenced in strategies: 150 (2.4% of total)
- Average cases per strategy: 3.4
- Cases appearing in multiple strategies: 72 / 150 (48%)

**Mapping structure**:
- Case → Strategy: many-to-many (72 cases appear in multiple strategies)
- Source struct → Strategy: one-to-many (26 structs → 44 strategies, ratio 1.69)

**Examples of struct aggregation**:
- `['divide']` struct → 3 strategies (S001 "Part-to-Whole Ratio", S002 "Percentage Change", S003 "Growth Rate")
- `['add', 'divide']` struct → 3 strategies (S006, S007, S008)
- `['multiply', 'divide']` struct → 3 strategies

**Interpretation**: Single program structure can represent multiple semantic strategies (e.g., divide = ratio OR percentage change OR growth rate). LLM abstraction groups cases by semantic similarity within same struct, producing multiple strategies per struct cluster.

---

## 3. Concrete Example

**Strategy S001**: Part-to-Whole Ratio
- **Source struct**: `['divide']`
- **Example IDs**: 6 cases from train
  - AAP/2006/page_85.pdf-1: "what is the percentage increase in inventories due to the adoption..."
  - PKG/2006/page_27.pdf-1: "what was the operating income margin for 2005?"
  - ETR/2011/page_145.pdf-2: (another divide-based question)
  - ... (3 more)

**Analysis**: Strategy S001 was abstracted from 6 different Cases with `['divide']` struct. No single Case corresponds to S001. When Stage 1-2 experiments retrieve S001 for a query, the retrieved strategy is NOT the abstraction of any specific retrieved Case—it's a composite abstraction from multiple historical cases.

---

## 4. Validity Classification: Which Stage 1-2 Results Remain Valid?

### VALID as Exploratory Evidence
- **Performance differences between arms** (None/Case/Strategy/Both): ✓ Valid
  - Demonstrates that memory retrieval affects reasoning performance
  - Shows heterogeneity across queries (oracle gap exists)
  - Evidence that different memory types have different utility profiles

- **Retrieval quality metrics**: ✓ Valid
  - Case retrieval: question+facts semantic similarity
  - Strategy retrieval: case-anchored candidate filtering
  - Hit/miss rates, top-k coverage

- **Confound identification**: ✓ Valid
  - Same-company train/test overlap (99/100 companies)
  - Same-report siblings
  - Cross-company case exclusion tested

- **Memory-induced failure modes**: ✓ Valid
  - Scale pollution (memory introduces wrong unit/scale)
  - Operation mismatch (retrieved strategy has wrong operator sequence)
  - Evidence conflicts

### INVALID for Paired Abstraction Claims
- **"Abstraction helps for complex reasoning"**: ✗ Cannot claim
  - Confounded: Strategy also aggregates multiple experiences, not pure abstraction
  - Cannot distinguish "abstraction benefit" from "aggregation benefit" or "coverage difference"

- **"Strategy > Case when X"**: ✗ Causal interpretation unclear
  - Strategy and Case have different source experiences
  - Cannot attribute performance difference to abstraction operator alone
  - Could be due to: semantic generalization, different evidence coverage, aggregation smoothing, or actual abstraction

- **"Abstraction transfers better across companies"**: ✗ Cannot claim
  - Same-company confound makes cross-company transfer untestable in current design
  - Strategy's better transfer could be due to removing company-specific details OR aggregating across companies

### REINTERPRETABLE with Correct Framing
Original Stage 1 findings can be reframed as:
- "Symbolic program templates (Strategy) vs concrete solved cases (Case) show different utility profiles"
- "Aggregated multi-example strategies provide different coverage than single-case retrieval"
- "Abstract representation (no company/year/values) retrieves differently than concrete representation"

These are valid exploratory findings about **representation effects**, not isolated **abstraction operator effects**.

---

## 5. Design Recommendation: Paired Construction for Stage 36

To enable controlled abstraction study, reconstruct memories with 1:1 pairing:

### Proposed Paired Construction

**Step 1**: Select source experiences E
- Sample N train experiences (e.g., N=100-500)
- Stratify by: struct family, company diversity, question complexity
- Ensure each E has valid program + sufficient context

**Step 2**: Create Case(E) for each E
- Preserve concrete details: company name, year, specific values, report context
- Include: question, gold_facts, program, answer
- Retrieval text: question + concrete facts

**Step 3**: Create Strategy(E) for each E via abstraction operator
- Apply deterministic or LLM-based abstraction:
  - Remove: company names, years, specific numbers, table row labels
  - Add: operand role bindings (V1=new_value, V2=old_value)
  - Preserve: program structure, operation sequence, semantic pattern
- Include: abstract question pattern, symbolic program template, role definitions
- Retrieval text: abstract pattern + template

**Step 4**: Maintain provenance linkage
- Each memory record includes `source_experience_id`
- Case(E) and Strategy(E) share same `source_experience_id`
- Enables paired analysis: compare Case(E) vs Strategy(E) on query Q

### Minimal Stage 36 Experiment Design

**Sample**: 30-50 test queries stratified by complexity/type

**Arms**: 
- None (no memory)
- Case(E) only (retrieve top-3 concrete cases)
- Strategy(E) only (retrieve top-3 abstract strategies)
- Paired(E) (retrieve top-3 E, present both Case(E) + Strategy(E) for same source)

**Key diagnostic**: 
- Does Case(E) vs Strategy(E) performance difference persist when both derive from same source?
- Does Paired(E) show complementarity (both representations from same source better than either alone)?

**Retrieval protocol**:
- Embed query → retrieve top-k E by source experience
- For Case arm: present Case(E)
- For Strategy arm: present Strategy(E)
- For Paired arm: present both Case(E) + Strategy(E)

**Controlled confound**: Source experience E is identical across comparisons, only representation differs.

---

## 6. Feasibility and Cost Estimate

### Paired Construction Cost
- **Source selection**: 200 train experiences → 0 API cost (deterministic sampling)
- **Case(E) creation**: 200 × direct copy → 0 API cost
- **Strategy(E) abstraction**: 200 × LLM abstraction → ~200 API calls
  - Assuming $0.005/call (DeepSeek V4 Flash) → $1.00
  - Cache enables dry-run reproducibility
- **QC scan**: Leak detection (company/year in Strategy) → deterministic script

**Total construction cost**: ~$1-2

### Stage 36 Experiment Cost
- **Test queries**: 30-50 from dev/test
- **Arms**: 4 (None/Case/Strategy/Paired)
- **API calls**: 50 queries × 4 arms = 200 calls
  - @ $0.005/call → $1.00 per run
  - 3 repeated runs → $3.00 total

**Total Stage 36 cost**: ~$4-5 (construction + experiments)

### Time Estimate
- Paired construction script: 2-3 hours
- QC validation: 1 hour  
- Stage 36 experiment: 1 hour
- Analysis: 2-3 hours

**Total time**: ~1 day

---

## 7. Alternative: Reuse Existing Data with Explicit Boundaries

If paired construction is deferred, current FinQA data can still support research with **explicit framing**:

### Valid Research Questions (Exploratory)
1. How do symbolic templates vs concrete examples affect retrieval precision?
2. Does removing company-specific details improve cross-company transfer?
3. What is the cost-benefit tradeoff of semantic abstraction vs raw case retrieval?

### Invalid Research Questions (Require Paired Design)
1. Does abstraction help reasoning when source experience is identical?
2. What is the pure effect of abstraction operator on downstream utility?
3. Are abstract representations better for compositional generalization?

**Recommendation**: If continuing with existing data, paper framing should be "Representation Effects in Memory-Augmented Financial QA" rather than "When Does Experience Abstraction Help?"

---

## 8. Summary and Next Steps

### Key Findings
1. ✓ FinQA Case Memory: 1:1 mapping from train samples (6,251 cases)
2. ✗ FinQA Strategy Memory: Aggregated from multiple cases (44 strategies from 150 cases via 26 struct clusters)
3. ✗ Case(i) and Strategy(j) do NOT share source experience E
4. ✓ Stage 1-2 results valid as exploratory, invalid for paired abstraction claims

### Validity Boundaries
- **Exploratory evidence**: Memory helps, different types have different profiles
- **Causal claims**: Cannot isolate abstraction operator effect without paired design

### Recommended Path Forward

**Option A: Construct Paired Memories (Controlled Study)**
- Build Case(E) + Strategy(E) from same source E
- Run minimal Stage 36 paired experiment (~$5, 1 day)
- Enables causal claims about abstraction operator

**Option B: Continue with Existing Data (Exploratory Study)**
- Reframe research question: representation effects, not abstraction isolation
- Focus on retrieval-conditioned analysis, cross-company transfer, oracle gap
- Acknowledge aggregation as confound in limitations

**User Decision Required**: Option A (paired construction) or Option B (reframe with existing data)?

---

## Artifacts
- Case Memory: `pilot/output/case_memory.json` (6,251 entries)
- Strategy Memory: `pilot/output/strategies.json` (44 entries)
- Construction scripts: `pilot/build_case_memory.py`, `pilot/build_strategy_memory.py`
- This audit: `pilot/FINQA_PAIRED_ABSTRACTION_AUDIT.md`
