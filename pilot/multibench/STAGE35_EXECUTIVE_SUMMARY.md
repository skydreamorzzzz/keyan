# Stage 35 Executive Summary: MultiHiertt Pipeline Repair Validation

**Date**: 2026-08-18  
**Status**: ✅ **COMPLETED — Decision: DROP MultiHiertt**

---

## What Was Done

**Causal validation experiment**: Test whether evidence coverage improvement translates to downstream performance improvement.

1. Selected 29 samples:
   - Group A (19): Coverage repaired by structured rendering (missing operands → operands present)
   - Group B (10): Control samples (already had full coverage)

2. Re-ran with structured rendering (2000-char limit, preserves table structure)

3. Compared against baseline (600-char HTML truncation from Stage 33)

4. Analyzed failure mode migration and per-sample outcomes

**Cost**: $0.145 (29 API calls), 4.0 seconds execution time

---

## Key Finding

**Evidence coverage improvement did NOT translate to performance improvement.**

### Results

| Group | Baseline EM | Structured EM | Gain | Interpretation |
|-------|-------------|---------------|------|----------------|
| **A** (coverage repaired) | 0.000 | 0.053 | **+0.053** | Only 1/19 correct after repair |
| **B** (control) | 0.000 | 0.200 | +0.200 | Control outperforms treatment |

**Group A breakdown** (19 samples with operands repaired):
- Coverage repair fixes answer: **1 (5.3%)**
- Coverage repair improves extraction but operation wrong: 3 (15.8%)
- Coverage repair with no extraction improvement: **15 (78.9%)**

### What This Means

**Expected failure mode migration did NOT occur**:
- Expected: "missing evidence" → "wrong operation"
- Observed: 15/19 samples still show extraction failures or N/A despite operands being present

**True bottleneck**: Model capability on hierarchical table extraction, NOT context truncation.

---

## Corrected Understanding

### Stage 34 Audit Claimed
> Context rendering is the dominant bottleneck. Fixing it should increase baseline from 0.117 to 0.25-0.35.

### Verification Shows
- **Partial truth**: Context rendering WAS a bottleneck (72% samples missing operands)
- **But NOT dominant**: Even when fixed, 18/19 repaired samples still fail
- **True bottleneck**: Model cannot extract from complex hierarchical tables

### Why the Prediction Failed

Ablation measured **necessary condition** (operands present) but assumed **sufficient condition** (model can use them).

The implicit assumption:
> If operands are present, model will extract them correctly.

This is **FALSE** for MultiHiertt hierarchical tables with DeepSeek V4 Flash.

---

## Decision: DROP MultiHiertt

### Rationale

1. **Causal test failed**: Coverage repair → 5.3% success rate, far below expected
2. **No cheap fix remains**: Would require different model, benchmark-specific engineering, or ground-truth preprocessing
3. **Baseline still too low**: ~0.14 EM, far below 0.30 threshold for memory research
4. **Incompatible with research strategy**: Paper studies abstraction effects, not dataset-specific extraction debugging
5. **Opportunity cost**: FinQA + TAT-QA are validated, ready for memory experiments

### Alignment with Paper Direction

**Current strategy**: When does experience abstraction help? Controlled study of concrete vs abstract representations.

**MultiHiertt requires**: Extensive benchmark-specific pipeline engineering just to get working baseline.

**Conclusion**: Incompatible. Research should study abstraction phenomena, not debug extraction failures.

---

## What We Learned

### About MultiHiertt Pipeline

**FACT**: Context truncation removes 72% of samples' required operands (Stage 34 Audit confirmed).

**FACT**: Structured rendering restores operands to 77.4% of samples (ablation confirmed).

**FACT**: Restoring operands improves EM by only +0.053 for repaired samples (verification).

**SUPPORTED INTERPRETATION**: DeepSeek V4 Flash cannot reliably extract from hierarchical tables even when evidence is present.

**UNRESOLVED HYPOTHESIS**: Would a more capable model (GPT-4, Claude Opus) succeed? (Not tested due to cost and research misalignment)

### Methodological Lessons

1. **Distinguish necessary from sufficient conditions**:
   - Ablation identified necessary condition violation (operands missing)
   - Verification tested sufficient condition (model can use operands)
   - Both must pass before claiming a fix

2. **Test causal claims with targeted experiments**:
   - Don't assume fixing gap will work
   - Run small-scale validation before committing to full pipeline

3. **Control groups reveal confounds**:
   - Group B showed structured rendering helps even without coverage issues
   - Without controls, would have misattributed all gains to coverage repair

4. **Baseline performance gates validity**:
   - <0.15 EM even after repairs → cannot study memory effects
   - Check model capability on base task before designing memory experiments

---

## Next Steps

### DO (in priority order)

1. **Archive MultiHiertt work**: Move to `pilot/multibench/archive/multihiertt/`
2. **Update memory**: Document decision and rationale
3. **Return to FinQA**: Stage 1 complete, known to work, ready for four-arm experiment
4. **Resume memory utility research**: Test abstraction effects on validated testbeds

### DO NOT

- ❌ Try different models on MultiHiertt
- ❌ Enhance MultiHiertt prompts
- ❌ Preprocess with ground-truth parsers
- ❌ Run full 60×4 four-arm
- ❌ Any further MultiHiertt debugging

### Why This Is Right

**Information gain analysis**:
- Fixing MultiHiertt: Uncertain gain, high cost, benchmark-specific
- Returning to FinQA: Known working baseline, direct path to research questions

**Scientific principle**: When a measurement instrument requires more engineering than the phenomenon being measured, discard the instrument.

---

## Artifacts

- Experiment script: `pilot/multibench/none_only_verification_experiment.py`
- Analysis script: `pilot/multibench/none_only_verification_analysis.py`
- Sample selection: `pilot/multibench/none_only_verification_samples.json`
- Cache: `pilot/multibench/output/multihiertt/none_only_verification_cache.jsonl`
- Full report: `pilot/multibench/output/multihiertt/NONE_ONLY_VERIFICATION_REPORT.md`
- Decision log: `pilot/DECISIONS_STAGE35.md`

---

## For Next Session

If user asks about MultiHiertt:
1. Explain Stage 35 causal validation failed (coverage repair → 5.3% success)
2. True bottleneck is model capability, not context truncation
3. Decision: DROP MultiHiertt, return to FinQA
4. Do NOT resume MultiHiertt work unless user explicitly overrides decision

If user asks to continue research:
1. Recommend returning to FinQA four-arm experiment
2. Focus: Test abstraction effects on retrieval relevance, reasoning alignment, utility
3. FinQA Stage 1 validated, ready for memory experiments
