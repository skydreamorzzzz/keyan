# Context Ablation Decision: Keep MultiHiertt with Structured Rendering

**Date**: 2026-08-18  
**Decision**: Option A - Fix MultiHiertt pipeline with structured table rendering  
**Status**: Approved for implementation

---

## Executive Summary

Deterministic offline ablation experiment demonstrates that **structured table rendering** achieves 77.4% full evidence coverage (41/53 samples) with minimal token cost increase (~745 tokens vs baseline 723). This satisfies the "cheap fix works" criterion for keeping MultiHiertt.

**Key finding**: Structured rendering achieves nearly identical coverage to 2000-char HTML (77.4% vs 75.5%) while using 35% fewer tokens (745 vs 1151).

---

## Ablation Results Summary

| Variant | Avg Coverage | Full Evidence % | Avg Tokens | Δ vs Baseline |
|---------|------------:|----------------:|-----------:|-------------:|
| 600-char HTML (baseline) | 0.498 | 41.5% | 723 | — |
| 2000-char HTML | 0.799 | 75.5% | 1151 | +34.0% |
| Structured table | 0.814 | 77.4% | 745 | +35.8% |

**Winner**: Structured table rendering
- Best coverage (77.4%)
- Lowest token cost among high-coverage variants (745)
- No external dependencies (regex-based fallback implemented)

---

## Decision Rationale

### Why Keep MultiHiertt (vs dropping for FinQA)

1. **Evidence bottleneck is fixable**: 77% coverage sufficient for valid memory utility research
2. **Low implementation cost**: Structured rendering already implemented in ablation script, can be directly integrated
3. **Zero API cost to verify**: Deterministic offline fix, no LLM calls needed
4. **Strategic value**: MultiHiertt's financial reasoning domain aligns with agent memory research goals

### Why Structured Rendering (vs 2000-char HTML)

1. **Token efficiency**: 35% fewer tokens (745 vs 1151) for same coverage
2. **Better interpretability**: Markdown-like format preserves row/column relationships
3. **No dependency**: Regex-based fallback works without BeautifulSoup
4. **Graceful degradation**: Falls back to truncated HTML if parsing fails

---

## Expected Performance Gains

### Current State (Stage 33 Four-arm Dry-Run)
- Baseline EM: 0.117
- Oracle gap: 0.017
- Evidence coverage: 41.5% samples with full evidence

### After Structured Rendering Fix
- **Expected baseline EM**: 0.25-0.35 (conservative estimate)
- **Expected oracle gap**: >0.05 (based on extraction improvements)
- **Evidence coverage**: 77.4% samples with full evidence

**Rationale for EM estimate**:
- Current failures: 53/60 samples (88%)
- Evidence missing: ~31/53 samples (58%)
- After fix: ~12/53 samples still missing evidence (23%)
- If half of newly-covered samples solve correctly → +19 samples → EM ~0.30

---

## Implementation Plan

### Step 1: Integrate Structured Rendering (15 minutes)
1. Copy `render_structured_table()` from `context_representation_ablation.py` to `multihiertt_four_arm_dry_run.py`
2. Replace `render_table_html_preview(html, limit=600)` calls with `render_structured_table(html, char_limit=2000)`
3. Update `VERSION` string to indicate structured rendering

### Step 2: Verification Run (30 minutes, ~60 API calls)
1. Re-run N=60 samples × 1 arm (none) with structured rendering
2. Compare EM against baseline 0.117
3. **Success criterion**: EM ≥ 0.25

### Step 3: Conditional Full Four-arm Run (if Step 2 succeeds)
1. If baseline EM ≥ 0.25, run full N=60 × 4 arms
2. Measure oracle gap
3. **Success criterion**: Oracle gap ≥ 0.05

### Step 4: Proceed to Memory Utility Research (if Step 3 succeeds)
1. Expand to full N=120 samples × 4 arms
2. Retrieval-conditioned analysis (hit vs miss) now meaningful
3. Research question: When does experience abstraction help?

### Fallback (if any step fails)
- Document failure mode
- Switch to FinQA (Stage 1 complete, known to work)
- No further MultiHiertt optimization attempts

---

## Cost-Benefit Analysis

### Costs
- Implementation: 15 minutes (copy-paste + integration)
- Verification: ~$0.30 (60 calls × DeepSeek V4 Flash pricing)
- Full four-arm (if needed): ~$1.20 (240 calls)
- Total risk: <$2 + 1 hour human time

### Benefits
- Unlock MultiHiertt for memory research (avoid dataset switch)
- Validate structured rendering approach (transferable to other benchmarks)
- Generate publication-quality diagnostic (context representation matters)
- Preserve Stage 31-33 infrastructure investment

**Verdict**: High ROI, low risk, proceed.

---

## Constraints Satisfied

✅ **Zero new API calls for diagnosis**: Ablation used cached data only  
✅ **Cheap fix criterion**: Structured rendering implementation <1 hour  
✅ **Deterministic verification**: Coverage metric computable offline  
✅ **No git operations**: Implementation proceeds in working tree only  
✅ **Strategic alignment**: MultiHiertt kept for "when does abstraction help?" research direction  

---

## Artifacts

- Ablation script: `pilot/multibench/context_representation_ablation.py`
- Results report: `pilot/CONTEXT_ABLATION_REPORT.md`
- This decision doc: `pilot/CONTEXT_ABLATION_DECISION.md`

---

## Next Action

Implement structured rendering in `multihiertt_four_arm_dry_run.py` and run verification (Step 1-2 above).

**User approval required before**:
- Running verification LLM calls (Step 2, ~60 calls)
- Running full four-arm experiment (Step 3, ~240 calls)
- Any git operations (commit, push, branch)
