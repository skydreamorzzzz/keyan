# Oracle Pilot 决策日志

所有关键实验设计决定与理由。

---

## Stage 35: None-only Verification — Pipeline Repair Causal Validation (2026-08-18)

**Objective**: Test whether evidence coverage improvement (via structured rendering) translates to downstream reasoning performance improvement.

**Background**: Stage 34 Audit identified context truncation as dominant bottleneck (600-char limit loses operands in 72% samples). Ablation showed structured rendering achieves 77.4% samples with full operands vs 41.5% baseline. This stage validates the causal link: coverage repair → performance gain.

### Experiment Design

**Method**: Re-run 29 selected samples with structured rendering, compare against baseline (600-char HTML).

**Sample Selection**:
- **Group A (n=19)**: Coverage repaired by structured rendering
  - Baseline: Missing ≥1 source operand
  - Structured: All source operands present
  - All had baseline answer = N/A or extraction failure
- **Group B (n=10)**: Control samples with full operand coverage in both conditions

**Variables**:
- **Changed**: Context rendering only (600-char HTML → structured table with 2000-char limit)
- **Frozen**: LLM (DeepSeek V4 Flash), evaluator, prompt structure, temperature (0), max_tokens (1400), retrieval, memory

**Cost**: 29 API calls × $0.005 = **$0.145**, execution time 4.0s

### Results

| Group | Baseline EM | Structured EM | Gain |
|-------|-------------|---------------|------|
| A (coverage repaired) | 0.000 | 0.053 | +0.053 |
| B (control) | 0.000 | 0.200 | +0.200 |

**Group A Breakdown** (19 samples with coverage repaired):
- Coverage repair → Answer correct: **1 (5.3%)**
- Coverage repair → Extraction improves but operation wrong: 3 (15.8%)
- Coverage repair → No extraction improvement: 15 (78.9%)
- Becomes worse: 0 (0.0%)

**Group B**: 2/10 control samples became correct (minor improvements from structure preservation, but 8/10 still failed).

### FACT: Evidence Coverage Improvement Did NOT Translate to Performance Gain

**Causal test failed**: Only 1/19 (5.3%) samples with repaired coverage became correct.

**Expected failure mode migration did NOT occur**:
- Expected: "missing evidence" → "wrong operation"
- Observed: 15/19 samples still show extraction failures (wrong values extracted or N/A) despite operands being present

**Control group outperformed treatment group**: Group B (+0.200) > Group A (+0.053), suggesting coverage repair is not the dominant factor.

### SUPPORTED INTERPRETATION: Model Capability is the Bottleneck

**Root cause**: DeepSeek V4 Flash cannot reliably extract values from complex hierarchical tables, even when operands are present.

**Evidence**:
1. Sample `8ca8fbf0...`: Gold `-2`, model extracted wrong values (781, 767) and computed wrong difference (14)
2. Sample `776342a2...`: Gold `-0.12537`, model output `-2,926` (wrong scale)
3. Sample `ab9c2862...`: Model still outputs `N/A` despite having required values

**Model struggles with**:
- Multi-level headers (hierarchical row/column structures)
- Cross-table references
- Conditional extraction ("In years where X > 250, sum Y")
- Unit/scale normalization (percentages, thousands)

**Structured rendering helps preserve structure, but model cannot reliably navigate complex layouts.**

### Decision: DROP MultiHiertt from Memory Research

**Rationale**:
1. **Cost-benefit fails**: Structured rendering fixes coverage but NOT performance
2. **Expected gain unrealized**: Baseline EM ~0.14, far below 0.30 threshold
3. **No cheap fix remains**: Further improvements require:
   - Different model (higher capability, higher cost)
   - Benchmark-specific prompt engineering (not generalizable)
   - Ground-truth table parsing (expensive preprocessing)
4. **Opportunity cost**: Continuing diverts effort from productive FinQA + TAT-QA research

**Alignment with research strategy**: Current paper direction is "when does experience abstraction help?" (controlled study of abstract vs concrete representations). MultiHiertt requires extensive benchmark-specific engineering just to get working baseline. **Incompatible**.

### Corrected Stage 34 Findings

**Stage 34 Audit claimed**: Context rendering is dominant bottleneck. Fixing it should increase baseline 0.117 → 0.25-0.35.

**Verification shows**:
- **Partial truth**: Context rendering WAS a bottleneck (missing operands)
- **But NOT dominant**: Even when fixed, model fails 18/19 repaired samples
- **True bottleneck**: Model capability on hierarchical table extraction

**Ablation prediction failed**: Assumed "if operands present → model extracts correctly." This is **FALSE** for MultiHiertt hierarchical tables.

### Methodological Lessons

**For pipeline diagnostics**:
1. **Distinguish necessary from sufficient conditions**: Coverage analysis (necessary), verification (sufficient). Both must pass.
2. **Test causal claims**: Ablation identified gap, verification tested if fixing gap helps.
3. **Control for confounds**: Group B showed structured rendering helps even without coverage issues.

**For dataset selection**:
1. **Baseline gates validity**: <0.15 even after repairs → cannot study memory effects
2. **Avoid benchmark-specific engineering**: Poor choice for studying general phenomena
3. **Model capability is prerequisite**: Cannot study retrieval/memory if model lacks base task capability

### Recommended Actions

**DO**:
1. Archive MultiHiertt work (move to `pilot/multibench/archive/multihiertt/`)
2. Document decision in DECISIONS.md and memory
3. Focus on FinQA + TAT-QA (simpler tables, higher baselines, known to work)
4. Resume memory utility research on validated testbeds

**DO NOT**:
- ❌ Try different models on MultiHiertt
- ❌ Enhance MultiHiertt prompts with table extraction examples
- ❌ Preprocess tables with ground-truth parsers
- ❌ Run full 60×4 four-arm
- ❌ Invest more time debugging MultiHiertt

**Why this is right**: When measurement instrument requires more engineering than phenomenon being measured, discard the instrument.

### Artifacts
- Experiment: `pilot/multibench/none_only_verification_experiment.py`
- Analysis: `pilot/multibench/none_only_verification_analysis.py`
- Sample selection: `pilot/multibench/none_only_verification_samples.json`
- Cache: `pilot/multibench/output/multihiertt/none_only_verification_cache.jsonl`
- Report: `pilot/multibench/output/multihiertt/NONE_ONLY_VERIFICATION_REPORT.md`

**Status**: ✅ **COMPLETED — Decision finalized: DROP MultiHiertt**

---

