# Decision 35: Context Representation Ablation - Keep MultiHiertt with Structured Rendering

**Date**: 2026-08-18  
**Status**: [IMPLEMENTED — awaiting user approval for verification run]  
**Estimated Cost**: <$2 + 1 hour implementation  
**Expected Gain**: Baseline EM 0.117 → 0.25-0.35

---

## Context

Stage 34 audit corrected Stage 34 diagnostic, establishing context rendering as dominant bottleneck:
- Evaluator bugs: 1/60 (not 6/60) — minimal impact
- Evidence coverage: 41.5% samples with full operands (baseline 600-char HTML)
- Context truncation: 23% of failures directly due to 600-char table limit

**Strategic constraint**: Paper direction shifted from "build adaptive router" to "when does abstraction help?" — MultiHiertt must be kept or dropped quickly, no prolonged optimization.

---

## Experiment: Context Representation Ablation

**Method**: Deterministic offline comparison of 3 rendering variants on 53 samples with gold programs
- Baseline: 600-char raw HTML preview
- Variant A: 2000-char raw HTML preview  
- Variant B: Structured table (markdown-like, preserves row/column relationships)

**Evidence metric**: Normalized source operand coverage (14,316 ↔ 14316, $10.2 ↔ 10.2)

**Results**:

| Variant | Coverage | Full Evidence % | Tokens | Δ vs Baseline |
|---------|----------|-----------------|--------|---------------|
| 600-char HTML | 49.8% | 41.5% (22/53) | 723 | — |
| 2000-char HTML | 79.9% | 75.5% (40/53) | 1151 | +34.0% |
| Structured | 81.4% | 77.4% (41/53) | 745 | +35.8% |

**Winner**: Structured rendering
- Best coverage: 77.4% samples with full evidence
- Token efficient: 745 tokens (vs 1151 for 2000-char HTML)
- No dependencies: Regex-based fallback (no BeautifulSoup required)

---

## Decision: Option A — Keep MultiHiertt with Structured Rendering

**Rationale**:
1. **Cheap fix works**: 77.4% evidence coverage sufficient for valid memory research (target was >70%)
2. **Token efficient**: 35% fewer tokens than 2000-char HTML for same coverage
3. **Low implementation cost**: <15 minutes (copy-paste structured rendering function)
4. **Low validation cost**: ~60 API calls ($0.30) to verify baseline improvement
5. **Strategic fit**: Keeps MultiHiertt for "when does abstraction help?" research

**Expected gains**:
- Baseline EM: 0.117 → 0.25-0.35 (conservative)
- Oracle gap: 0.017 → >0.05 (unlocks memory utility signal)
- Research validity: Restored

---

## Implementation Steps

### Step 1: Integrate Structured Rendering ✅ COMPLETE
- Copied `render_structured_table()` to `multihiertt_four_arm_dry_run.py`
- Modified `render_context()` to use structured rendering
- Updated VERSION to `multihiertt_four_arm_dry_run_v3_structured_20260818`

### Step 2: Verification Run [AWAITING USER APPROVAL]
- Re-run N=60 samples × 1 arm (none) with structured rendering
- Cost: ~60 API calls (~$0.30)
- Success criterion: EM ≥ 0.25

### Step 3: Conditional Full Four-arm [PENDING STEP 2]
- If Step 2 succeeds, run N=60 × 4 arms
- Cost: ~240 API calls (~$1.20)
- Success criterion: Oracle gap ≥ 0.05

### Fallback
- If either step fails → switch to FinQA (Stage 1 complete)
- No further MultiHiertt optimization

---

## Constraints Satisfied

✅ Zero API cost for diagnosis (used cached data)  
✅ Cheap fix criterion (<1 hour implementation)  
✅ Deterministic verification (coverage computable offline)  
✅ Strategic alignment (keeps MultiHiertt for abstraction research)  
✅ No git operations (working tree only)  

---

## Key Insight: Structured Rendering Advantage

Structured rendering achieves better coverage than raw HTML by:
1. **Preserving relationships**: Row/column headers remain associated with cells
2. **Removing noise**: HTML tags, styling, nested structures stripped
3. **Uniform format**: Consistent markdown table format easier for LLM to parse
4. **Compact representation**: Same information in fewer tokens

Example: `uid=776342a2d8c14922`
- 600-char HTML: Missing operand at position 679 (truncated)
- Structured: Both operands visible in clean table format within 600-char equivalent

---

## Artifacts

- Ablation script: `pilot/multibench/context_representation_ablation.py`
- Results: `pilot/CONTEXT_ABLATION_REPORT.md`
- Decision doc: `pilot/CONTEXT_ABLATION_DECISION.md`
- Modified code: `pilot/multibench/multihiertt_four_arm_dry_run.py` (v3_structured)

---

## Next Session Guidance

**If user approves Step 2 verification**:
1. Run verification: `DRY_RUN_N=60, single arm (none)`
2. Report EM vs baseline 0.117
3. If EM ≥ 0.25 → proceed to Step 3 (four-arm)
4. If EM < 0.25 → investigate failure, likely switch to FinQA

**If user rejects MultiHiertt**:
1. Switch to FinQA immediately
2. Leverage Stage 1 complete infrastructure
3. No further MultiHiertt work

**Constraints remain**:
- No git operations without explicit permission
- Minimize API calls (verification only)
- No strategy retrieval optimization until baseline valid
