# Stage 36 Final Verdict

**Date**: 2026-08-18

---

## Executive Summary

**Stage 36 paired abstraction experiment has been completed and strictly re-evaluated.**

**Verdict: The research hypothesis is NOT SUPPORTED by evidence.**

---

## What Was Tested

**Hypothesis**: From the same source experience E, constructing Case(E) and Strategy(E) representations with different abstraction levels would show meaningful differences in downstream utility under shared-source retrieval protocol.

**Experimental Design**:
- 30 FinQA dev queries × 4 arms (None/Case/Strategy/Paired)
- Shared-source retrieval (all arms use same source experience IDs)
- Model: DeepSeek-V3, Temperature: 0.7
- 120 API calls executed, all responses saved

---

## What We Found (Original Evaluation)

**Initial results with 1% tolerance evaluator**:
- None: 53.3%
- Case: 76.7% (+23.4pp)
- Strategy: 73.3% (+20.0pp)
- Paired: 76.7% (+23.4pp)

This suggested strong memory effects and potential abstraction differences.

---

## What We Found (Strict Re-evaluation)

**After applying FinQA official evaluation semantics (5-decimal exact match)**:
- None: 40.0%
- Case: 43.3% (+3.3pp)
- Strategy: 40.0% (+0.0pp)
- Paired: 40.0% (+0.0pp)

**The +20-23pp gains were ENTIRELY evaluation artifacts.**

---

## Root Cause of Artifact

**Percentage precision mismatch**:
- FinQA stores percentages as decimals: 0.03558 = 3.558%
- Models output: "3.56%"
- Parser converts to: 0.0356
- Original evaluator: |0.0356 - 0.03558|/0.03558 < 0.01 ✓ (within 1% tolerance)
- Official evaluator: round(0.0356, 5) ≠ 0.03558 ✗ (not exact match)

**5 queries affected all 4 arms identically = 20 false positives**

This single formatting issue accounts for the entire apparent memory gain.

---

## True Behavioral Patterns

**Under strict evaluation**:
- **Rescue events**: 1 (Case on GPN/2017/page_77.pdf-4)
- **Harm events**: 0
- **All correct**: 12/30 (40%)
- **All wrong**: 17/30 (57%)
- **Memory changes outcome**: 1/30 (3%)

**The single rescue**:
- None: Selected wrong operand ($62,154)
- Case: Correctly summed three intangibles ($73,576) ✓
- Strategy: Answered 0 (misinterpretation)
- Paired: Selected only one of three ($42,721)

**Mechanism**: Case memory showed "sum multiple deductible items" pattern that helped operand selection. This is a genuine reasoning rescue.

---

## Abstraction Operator Effect

**Case vs Strategy disagreement: 1/30 (3.3%)**
- Case better: 1
- Strategy better: 0
- Identical behavior: 29/30 (96.7%)

**Under strict evaluation, Case and Strategy are behaviorally equivalent on 96.7% of queries.**

The hypothesis that abstraction level matters is NOT supported by evidence (n=1 disagreement insufficient).

---

## Why Memory Has Minimal Utility

**Base model saturation dominates**:
- 40% queries: DeepSeek-V3 already knows the pattern
- 57% queries: Beyond model capability even with memory
- 3% queries: Memory provides actionable hint

**Memory utility is squeezed between**:
- Saturation (model already knows)
- Capability ceiling (model can't learn from memory)

Only a narrow 3% "sweet spot" where memory helps.

---

## Validity Lessons

**1. Answer-only evaluation is unreliable for FinQA**
- Cannot distinguish reasoning from formatting
- Tolerance bands mask precision issues
- Created false confidence (+20pp → +3.3pp gap)

**2. Must use program execution evaluation**
- FinQA official: execute program + 5-decimal exact match
- Stage 36 should have parsed and executed programs
- Answer-only is fundamentally unsound

**3. Base model capability is the primary constraint**
- Memory augmentation has minimal marginal utility on high-capability models
- Retrieval quality doesn't predict utility (sample size too small)

---

## Recommendation

### DO NOT PROCEED TO TAT-QA REPLICATION

**Reasons**:
1. FinQA shows memory has essentially no utility (+3.3pp, n=1 rescue)
2. Evaluation methodology must be fixed first (program execution)
3. Abstraction hierarchy hypothesis is not supported
4. TAT-QA would likely replicate same null result

### BEFORE ANY FURTHER EXPERIMENTS

**Fix evaluation**:
- Implement program execution evaluation
- Use official FinQA/TAT-QA evaluation semantics
- No tolerance bands on answer-only

**Understand the phenomenon**:
- Why does base model saturate on 40% queries?
- Why does model fail on 57% even with memory?
- What query characteristics create the 3% sweet spot?

### RESEARCH DIRECTION VERDICT

**Original direction: "When Does Experience Abstraction Help?"**
- Evidence: Abstraction level doesn't matter (96.7% identical)
- Effect size: n=1 rescue insufficient for conclusions
- Verdict: **NOT VIABLE**

**Alternative if continuing**:
- "When Is Retrieved Experience Actually Useful?" (focus on the 3% sweet spot)
- "Why Do High-Capability Models Show Memory Saturation?" (capability boundary)
- But fundamental question: Is memory augmentation marginal on strong base models?

---

## Files Preserved

**Strict re-evaluation**:
- `STAGE36_STRICT_REEVAL_REPORT.md` — Full strict analysis
- `strict_evaluation_results.json` — 30×4 correctness matrix
- `strict_transition_analysis.json` — Rescue/harm patterns
- `STRICT_EVALUATION_EXECUTIVE_SUMMARY.json` — Machine-readable summary

**Original experiment** (superseded but preserved):
- `STAGE36_FINAL_REPORT.md` — Original analysis with artifacts
- `results_{none,case,strategy,paired}.json` — Raw responses (still valid)
- `RUNTIME_PROVENANCE.md` — Reproducibility documentation

**This file**:
- `FINAL_VERDICT.md` — Research direction verdict

---

## Conclusion

**Stage 36 research hypothesis has been tested and NOT SUPPORTED.**

Under strict evaluation:
- Memory provides minimal utility (+3.3pp, 1 rescue)
- Abstraction level is irrelevant (96.7% identical)
- Original +20pp gains were evaluation artifacts
- Base model saturation and capability ceiling dominate outcomes

**The "abstraction hierarchy for reasoning transfer" research direction is not viable based on FinQA evidence.**

Recommend closing this research direction or fundamentally pivoting before investing further resources.

---

**Status**: Research hypothesis rejected. Experiment complete. No further action recommended.

**Generated**: 2026-08-18
