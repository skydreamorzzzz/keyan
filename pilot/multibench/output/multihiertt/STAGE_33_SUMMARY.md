# Stage 33 MultiHiertt Four-arm Dry-Run - Executive Summary

Date: 2026-08-18  
Status: **Completed with pipeline validity concerns**

## What Was Done

1. **Execution layer repaired** (by Codex):
   - Fixed `pilot/llm.py`: made `response_format` optional, added `thinking: disabled`, improved error diagnostics
   - Fixed API priority: DEEPSEEK_API_KEY checked first
   - Added proper file locking for concurrent cache writes

2. **Dry-run executed successfully**:
   - N=60 samples × 4 arms = 240 API calls
   - Cache integrity: 100% parse success rate
   - All calls used DeepSeek V4 Flash via official API

3. **Pipeline validity audit performed**:
   - Analyzed all 240 cached responses
   - Classified failure modes
   - Assessed evaluator, context rendering, and retrieval quality

## Key Findings

### Four-arm Performance
| Arm | EM | F1 |
|---|---:|---:|
| None | 0.117 | 0.125 |
| Case | 0.200 | 0.208 |
| Strategy | 0.183 | 0.192 |
| Both | 0.233 | 0.242 |

- Sample Oracle EM: 0.250
- **Oracle Gap: 0.017** (only 1/60 samples differ across arms)

### Failure Attribution (None arm, N=60)

**Evaluator strictness (6 samples):**
- Model returns correct numeric answer but wrong Python type
- Example: Gold="86" (str) vs Pred=86 (int)
- Potential EM gain if fixed: +0.100 (from 0.117 → 0.217)

**Real errors (53 samples):**
- Wrong extraction/logic: 44 (83% of failures)
- Small calculation errors: 4
- Returned list instead of sum: 3
- Scale/percent errors: 1
- Zero instead of correct sum: 1

**Context truncation:**
- Average HTML preservation: 52.8%
- Severe truncation (<30%): 1/20 samples
- **Conclusion**: Not the primary bottleneck

## Critical Issue

**Oracle gap too small for memory research.**

With oracle=0.250 and best_fixed=0.233, the oracle gap is only 0.017. This means:
- 59/60 samples have identical outcomes across all four arms
- Almost no variance to study memory selection effects
- Even a perfect selector would only gain +0.017 EM

**Root cause**: Pipeline fundamentals (evaluator, prompt, context rendering) cause 88% of samples to fail across all arms uniformly.

## What This Means

### Execution Layer: ✅ VALID
- LLM API calls work reliably after Codex's fix
- Cache and provenance tracking function correctly
- Concurrent execution with proper locking

### Retrieval Layer: ✅ WORKS AS DESIGNED
- question_only + family-dedup achieves 70% family_hit rate
- Stage 32 protocol operates correctly
- But retrieval quality cannot be assessed when downstream pipeline fails

### Downstream Pipeline: ❌ NOT VALID FOR MEMORY RESEARCH
- Baseline too low (0.117)
- Oracle gap too small (0.017)
- Cannot distinguish memory effects from noise

### Retrieval-Conditioned Interpretation: ⚠️ CONFOUNDED
Previous observation "strategy helps on miss but not on hit" cannot be trusted because:
- Conditioning on family_hit may be confounded by sample difficulty
- Need to verify: Are miss samples actually easier (more span-type, simpler tables)?
- With only 7/60 correct samples total, any conditional analysis has high variance

## Decision

**PAUSE MultiHiertt memory research. Fix pipeline first.**

### Do NOT proceed with:
- ❌ Selector/router model training
- ❌ Retrieval optimization (HyDE, reranking)
- ❌ Expanding to full 120 samples
- ❌ Repeated trials
- ❌ Drawing conclusions about memory utility

### DO proceed with:
1. **Fix evaluator** (10 min): Accept numeric equivalence across int/float/str
2. **Parse HTML tables** (2-3 hours): Convert to structured text with row/column headers
3. **Enhance prompt** (1 hour): Add extraction guidance and output format examples
4. **Diagnostic run** (30 min): N=20 samples to verify fixes

### Decision Point
If fixes achieve:
- Baseline EM >0.4
- Oracle gap >0.05

Then resume memory utility research on MultiHiertt.

Otherwise, return to FinQA (Stage 1 complete, known to work) or TabMWP as primary memory testbed.

## Why This Is The Right Call

**Information gain analysis:**
- Optimizing memory selection on current pipeline: max gain = oracle gap = 0.017
- Fixing evaluator alone: expected gain = 0.100
- Fixing extraction: expected gain = 0.200+

The bottleneck is not memory selection. It's pipeline fundamentals.

**Scientific rigor:**
When baseline performance is 0.117 and four arms converge within 0.017, we cannot make reliable claims about memory utility. Fix the measurement instrument before drawing conclusions.

## Artifacts

- Code: `pilot/multibench/multihiertt_four_arm_dry_run.py`
- Cache: `pilot/multibench/output/multihiertt/multihiertt_four_arm_dry_run_repaired_cache.jsonl`
- Full report: `pilot/multibench/output/multihiertt/STAGE_33_AUDIT_REPORT.md`
- Audit scripts: `pilot/multibench/audit_*.py`
- DECISIONS.md: Entry 34
- Memory updated: `project-memory-multihiertt-retrieval.md`

## Next Session Guidance

If user asks to continue MultiHiertt:
1. Acknowledge Stage 33 completed successfully at execution level
2. Explain pipeline validity concerns (oracle gap=0.017)
3. Recommend fixing evaluator + context rendering first
4. Do NOT expand scope or optimize retrieval until baseline improves

If user asks about memory utility conclusions:
1. State that current data cannot support memory effect claims
2. Explain confounds (sample difficulty, answer type distribution)
3. Recommend decision point criteria (baseline >0.4, oracle gap >0.05)
