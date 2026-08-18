# Research Direction Assessment: Abstraction Study Feasibility

**Date**: 2026-08-18  
**Context**: After MultiHiertt dropped (Stage 35) and FinQA memory audit completed, assess feasibility of controlled abstraction study vs returning to exploratory memory research.

---

## Current State

### MultiHiertt: DROPPED
- **Stage 35 causal validation**: Coverage repair (missing operands → operands present) did NOT translate to performance gain (+0.053 EM for repaired group)
- **True bottleneck**: Model capability on hierarchical table extraction, not just context truncation
- **Baseline**: ~0.14 EM, far below 0.30 threshold for memory research
- **Decision**: DROP from memory utility research (see `DECISIONS_STAGE35.md`)

### FinQA: Memory Construction Audit Complete
- **Case Memory**: 6,251 entries, 1:1 from train samples ✓
- **Strategy Memory**: 44 entries, aggregated from 150 cases via struct clustering ✗
- **Finding**: NOT paired abstraction—Strategy abstracts from MULTIPLE cases, not single source
- **Implication**: Existing Stage 1-2 results valid as exploratory, invalid for paired abstraction claims
- **Audit report**: `FINQA_PAIRED_ABSTRACTION_AUDIT.md`

### TAT-QA: Pipeline Ready
- **Case Memory**: 13,215 train cases, retrieval audit complete (Stage 17)
- **Strategy Memory**: 30 strategies v0, HyDE retrieval frozen (Stage 21)
- **Four-arm small dry-run**: 30 samples, technically works (Stage 22-23)
- **Held-out diagnostic**: 120 samples, stability audit complete (Stage 24-25)
- **Baseline**: None EM=0.708, Oracle Gap=+0.089 (3-run mean)
- **Status**: Stable heterogeneity confirmed, ready for research

---

## Research Question Realignment

### Original Direction (User's Latest Directive)
> "When Does Experience Abstraction Help? A Controlled Study of Concrete and Abstract Experience Representations"

**Core requirement**: Case(E) and Strategy(E) must derive from **same source experience E** to isolate abstraction operator effect.

**Problem**: Current FinQA/TAT-QA/MultiHiertt Strategy memories all aggregate multiple cases, violating paired design.

### Updated Options

#### Option 1: Build Paired Memories (Controlled Study)
**What**: Reconstruct FinQA or TAT-QA with 1:1 paired Case(E) + Strategy(E) from same source E

**Pros**:
- Enables causal claims about abstraction operator
- Controlled design isolates confounds
- Aligns with "when does abstraction help?" framing

**Cons**:
- Requires new memory construction (~200 paired entries)
- ~$1-2 construction cost + $3-5 experiment cost
- ~1 day implementation time
- Existing Stage 1-2/17-25 results become exploratory context only

**Key question**: Is abstraction operator itself the phenomenon of interest, or is representation effect sufficient?

#### Option 2: Reframe as Representation Effects (Exploratory Study)
**What**: Continue with existing aggregated memories, study representation effects without causal abstraction claims

**Research questions**:
1. How do symbolic templates vs concrete examples affect retrieval precision?
2. Does removing company-specific details improve cross-company transfer?
3. What is the utility-cost tradeoff of abstract vs concrete memory?
4. When does memory help reasoning, and what types of memory help when?

**Pros**:
- Leverages existing validated pipelines (FinQA Stage 1-2, TAT-QA Stage 17-25)
- No reconstruction cost
- Can proceed immediately
- Addresses practically relevant questions

**Cons**:
- Cannot claim "abstraction helps" causally—only "abstract representation differs from concrete"
- Aggregation remains confound
- Less theoretically clean

**Framing**: "Memory Representation Effects in Experience-Augmented Financial QA" rather than "When Does Abstraction Help?"

#### Option 3: Hybrid Approach
**What**: 
1. Run minimal paired feasibility experiment on subset (e.g., 50 FinQA pairs, Stage 36)
2. If paired design shows clear signal, expand and pursue controlled study
3. If signal weak or confounded, pivot to exploratory representation study

**Pros**:
- Low upfront cost (~$5, 1 day)
- Tests whether abstraction isolation is empirically fruitful before full commitment
- Preserves optionality

**Cons**:
- Two-stage design may fragment narrative
- Risk of inconclusive Stage 36 result

---

## Hypothesis Re-evaluation

User originally outlined H1-H5 about abstraction effects. Reassess evidence under current findings:

### H1: Abstraction improves retrieval relevance
**Status**: **Partially supported (exploratory)**
- TAT-QA: semantic-rich strategy retrieval < schema-only (family top3: 0.216 vs 0.324)
- But: semantic abstraction helps lookup types, hurts arithmetic
- MultiHiertt: question_only > full_context (family top3: 0.532 vs 0.216)
- **Confound**: Cannot distinguish "abstraction" from "query representation" or "aggregation smoothing"

**Claim validity**:
- ✓ Valid: "Removing context details changes retrieval profile"
- ✗ Invalid: "Abstraction operator improves relevance" (no isolation)

### H2: Abstraction improves reasoning alignment
**Status**: **Inconclusive**
- FinQA Stage 1: Strategy arm weaker than Case on execution accuracy
- TAT-QA: Strategy ≈ Case (both < None in some runs)
- **Confound**: Strategy aggregates multiple cases, may have semantic drift or structural mismatch

**Claim validity**:
- ✓ Valid: "Abstract templates don't always align better than concrete examples"
- ✗ Invalid: "Abstraction degrades reasoning" (confounded by aggregation)

### H3: Abstraction reduces interference
**Status**: **No evidence**
- Not directly tested in existing experiments
- Would require controlled paired design to test

### H4: Abstraction enables compositional transfer
**Status**: **Weak exploratory signal**
- FinQA: Same-company confound prevents cross-company transfer test
- TAT-QA: Multi-span benefits from Case/Both, span benefits from Strategy in some samples
- **Confound**: Transfer could be due to aggregation (averaging over diverse cases) rather than abstraction

**Claim validity**:
- ✓ Valid: "Abstract representation has different transfer profile"
- ✗ Invalid: "Abstraction enables better generalization" (no isolation)

### H5: Utility depends on query-memory alignment
**Status**: **Supported (exploratory)**
- FinQA Stage 3-4: Stable heterogeneity exists, oracle gap +8.9pp
- TAT-QA Stage 25: Stable deviation events (None>Both, Strategy>Both)
- Retrieval-conditioned analysis shows differential utility
- **Valid finding**: Memory utility is query-dependent

**Claim validity**:
- ✓ Valid: "Different memory types have different utility profiles"
- ✓ Valid: "Utility is heterogeneous and partially predictable"
- ✗ Invalid: "Abstraction specifically helps certain query types" (aggregation confound)

### Summary: H1-H5 Under Current Design
- **H1, H2, H4**: Exploratory signals, but causal claims invalid (aggregation confound)
- **H3**: Not tested
- **H5**: Strongly supported, independent of abstraction isolation

**Implication**: If research goal is "when does memory help" (H5), existing data sufficient. If goal is "when does abstraction help" (H1-H4), need paired design.

---

## Novelty Boundaries

### What Existing Work Has Shown
- **Memory-augmented QA**: Retrieval improves performance (Lewis et al. 2020 RAG, Borgeaud et al. 2022 RETRO)
- **Case-based reasoning**: Concrete examples help (Aamodt & Plaza 1994, Kolodner 1992)
- **Abstract schemas**: Templates enable transfer (Gick & Holyoak 1983, Elio & Scharf 1990)
- **Hybrid memory**: Multiple memory types complement (Anderson 1983 ACT*, VanLehn 1996)

### Potential Novel Contributions (Conditional on Design Choice)

#### If Paired Abstraction Study (Option 1)
- **Novel**: First controlled isolation of abstraction operator effect in LLM memory augmentation
- **Novel**: Causal evidence for when abstraction helps vs hurts in financial reasoning
- **Novel**: Paired Case(E) vs Strategy(E) comparison on identical source experiences

#### If Representation Effects Study (Option 2)
- **Novel**: Systematic characterization of concrete vs abstract memory representations in financial QA
- **Novel**: Retrieval-conditioned utility analysis (hit/miss differential)
- **Novel**: Multi-benchmark comparison (FinQA, TAT-QA) of representation effects
- **Not novel**: General finding that "memory helps" (already established)

#### If Minimal Paired Feasibility (Option 3)
- **Novel**: First test of whether abstraction isolation is empirically fruitful in this domain
- **Novel**: Paired design methodology for memory ablation
- **Risk**: May be too small-scale for publication if inconclusive

---

## Recommendation

### Immediate Next Step: Minimal Paired Feasibility (Option 3)

**Rationale**:
1. **Low cost**: ~$5, 1 day implementation
2. **High information gain**: Tests whether paired design shows measurable signal before full commitment
3. **Preserves optionality**: If successful → expand to Option 1; if weak → pivot to Option 2
4. **Addresses uncertainty**: Current unknown whether abstraction operator effect is large enough to detect

### Stage 36 Minimal Paired Feasibility Design

**Scope**: 50 FinQA test queries, 4 arms

**Construction**:
- Select 200 train experiences (stratified by struct, company, complexity)
- Create Case(E): preserve concrete details
- Create Strategy(E): apply abstraction operator (remove company/year/values, add role bindings)
- Link via `source_experience_id`

**Arms**:
- **None**: No memory
- **Case**: Retrieve top-3 Case(E) by source experience similarity
- **Strategy**: Retrieve top-3 Strategy(E) by source experience similarity  
- **Paired**: Retrieve top-3 E, present both Case(E) + Strategy(E)

**Primary diagnostic**:
- Does Case vs Strategy difference persist when both from same source?
- Does Paired(E) show complementarity?
- Is effect size large enough for controlled study?

**Decision gate**:
- If Case vs Strategy Δ > 3pp AND statistically detectable → expand to full paired study
- If Paired > max(Case, Strategy) with gain > 2pp → complementarity exists, proceed
- If effects < 2pp or unstable → pivot to exploratory representation study

**Cost**: ~$5 total
**Time**: ~1 day
**Output**: Go/no-go decision on full paired study

---

## What NOT To Do

### ❌ Do NOT: Immediately build full paired study without feasibility test
- Risk: Commit 1-2 weeks to reconstruction, then find signal too weak to detect
- Alternative: Run Stage 36 minimal test first

### ❌ Do NOT: Continue MultiHiertt debugging
- Stage 35 confirmed: model capability bottleneck, not context alone
- Baseline too low (<0.15) even after fixes
- Opportunity cost: FinQA/TAT-QA are validated and ready

### ❌ Do NOT: Claim causal abstraction effects from existing FinQA/TAT-QA data
- Strategy memories aggregate multiple cases
- Cannot isolate abstraction operator without paired design
- Frame as exploratory representation effects only

### ❌ Do NOT: Build adaptive router without addressing baseline validity
- FinQA Stage 4B: Signal disappeared under conservative selection
- TAT-QA: Heterogeneity exists but router not developed
- Router research requires working baseline + clear oracle gap first

### ❌ Do NOT: Run more MultiHiertt experiments with current pipeline
- Already determined: pipeline not viable for memory research
- Any further work must first fix rendering + prompt, then re-validate baseline

---

## Summary: Path Forward

1. **Immediate** (1 day, ~$5):
   - Stage 36: Minimal paired feasibility on FinQA (50 queries, 200 paired memories)
   - Decision gate: effect size > 2-3pp and detectable?

2. **If Stage 36 shows signal** (1-2 weeks):
   - Expand to full paired study (500-1000 pairs, 200+ test queries)
   - Research question: "When Does Experience Abstraction Help?"
   - Novel contribution: Causal isolation of abstraction operator

3. **If Stage 36 shows weak/no signal** (pivot):
   - Proceed with exploratory representation study on existing data
   - Research question: "Memory Representation Effects in Financial QA"
   - Novel contribution: Systematic characterization across benchmarks

4. **Do NOT**:
   - Resume MultiHiertt (dropped after Stage 35)
   - Claim causal abstraction effects without paired design
   - Build router before baseline validity established

**User Decision Required**: 
- Approve Stage 36 minimal paired feasibility? 
- Or directly choose Option 1 (full paired) or Option 2 (exploratory reframing)?
