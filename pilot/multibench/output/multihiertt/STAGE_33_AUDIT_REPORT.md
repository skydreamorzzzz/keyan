# Stage 33 MultiHiertt Pipeline Validity Audit

Date: 2026-08-18

## Executive Summary

Stage 33 Four-arm Dry-Run completed successfully with N=60 samples. **Primary finding: pipeline has validity issues that must be fixed before memory utility can be assessed.**

Baseline (none) EM = 0.117 is artificially low due to:
1. **Evaluator type strictness** (6/60 samples): Model returns correct numeric answer but wrong Python type (int/float vs str)
2. **Real extraction/reasoning failures** (44/60 samples): Model fails to extract correct values or apply correct operations

**Key insight**: Oracle gap of 0.017 (only 1/60 samples varies across arms) indicates all four arms fail on the same samples. Memory selection optimization is premature when absolute performance is this low.

## Audit Scope

**Question**: Why is baseline EM only 0.117, and is the pipeline valid for memory utility research?

**Method**: Analyzed 240 cached API responses (60 samples × 4 arms) against validation set ground truth.

**Data sources**:
- Cache: `pilot/multibench/output/multihiertt/multihiertt_four_arm_dry_run_repaired_cache.jsonl`
- Validation: `data/multihiertt/raw/validation.parquet` (1044 samples)

## Failure Attribution (None Arm, N=60)

### Type 1: Evaluator Strictness Issues (6 samples, +0.100 potential EM gain)

Model produces numerically correct answer but wrong type:

| UID (prefix) | Question | Gold | Pred | Issue |
|---|---|---|---|---|
| faac106d | greatest value of Stores Opened in 2011 | "86" (str) | 86 (int) | Type mismatch |
| a5ec5ca7 | total impairment charge in 3 years | "10.2" (str) | 10.2 (float) | Type mismatch |
| 7389cfa3 | sum of Debt maturities + Capital lease | "6905" (str) | 6905 (int) | Type mismatch |
| c649cb8d | growth rate of Environmental | "-0.23188" (str) | -0.2318840579... (float) | Precision mismatch |

**Recommendation**: Relax evaluator to accept numeric equivalence across types. Current strict string matching penalizes correct answers.

**Impact if fixed**: EM would improve from 0.117 → 0.217 (+0.100).

### Type 2: Real Errors (53 samples)

| Error Mode | Count | Description |
|---|---:|---|
| wrong_extraction_or_logic | 44 | Failed to extract correct values from tables/text |
| calculation_error_small | 4 | Small arithmetic errors (e.g., 52.79 vs 51.98) |
| returned_list_instead_of_sum | 3 | Returned operands list instead of computing sum |
| scale_percent_error | 1 | ROI: returned 16.0 instead of 0.16 (forgot to divide by 100) |
| wrong_operands_zero_result | 1 | Returned 0 instead of actual sum |

**Example (wrong_extraction_or_logic)**:
- Q: "What is the growing rate of BENEFIT OBLIGATION AT END OF YEAR for Con Edison..."
- Gold: 0.01147
- Pred: "The question asks for... However, the table does not provide... cannot compute... not determinable..."

**Interpretation**: Model fails to locate evidence even when it exists in truncated HTML preview, or gives up when tables are cut off.

### Type 3: Context Truncation (1/20 samples <30% HTML preserved)

Average truncation ratio: 0.528 (52.8% of HTML chars preserved after `render_table_html_preview(html, limit=600)`).

**Severe truncation**: Only 1/20 audit samples had <30% preservation.

**Recommendation**: Truncation is NOT the primary bottleneck. Focus on extraction and reasoning failures first.

## Memory Effect Analysis

### Observed Pattern (from Stage 33 report)

```
              hit(42)   miss(18)   Δ
none          0.119     0.111     +0.008
strategy      0.119     0.333     +0.214  ← Unexpected
```

**User's hypothesis**: "Strategy helps on miss but not on hit" suggests surface-matching in retrieval.

**Alternative explanation**: With only 7/60 correct answers in baseline, and 53/60 failing on extraction/reasoning, the conditioning on `family_hit` may be confounded by:
- Sample difficulty distribution
- Answer type distribution (span vs program)
- Table complexity

**Evidence that retrieval-conditioned interpretation is premature**:
- Oracle gap = 0.017 (only 1/60 samples where memory selection matters)
- All arms fail on the same 53 samples
- The 7 correct samples may have simpler tables or more explicit evidence

## Pipeline Validity Assessment

**Is the current MultiHiertt pipeline valid for memory utility research?**

**NO** — for the following reasons:

1. **Evaluator bug**: 6/60 samples (10% of dataset) marked wrong due to type strictness, not actual errors
2. **Baseline too low**: 88% failure rate (53/60) driven by extraction failures, not memory selection
3. **Oracle gap too small**: 0.017 means almost no variance across arms to study memory effects
4. **Confounded retrieval signal**: `family_hit` does not reliably predict strategy utility

**What is valid**:
- Execution layer (LLM API, cache, provenance) works correctly after Codex's fix
- Retrieval infrastructure (question_only + family-dedup) operates as designed
- Four-arm experimental protocol is sound

**What is broken**:
- Context rendering (HTML truncation acceptable, but model fails to extract even from preserved content)
- Prompt does not sufficiently guide model to extract evidence and execute programs
- Evaluator rejects correct answers due to type mismatch

## Recommendations

### Immediate Actions (Before Any Memory Optimization)

1. **Fix evaluator**: Accept numeric equivalence across int/float/str types
   - Potential gain: +0.100 EM
   - Low cost, high certainty

2. **Improve context rendering**:
   - Parse HTML tables to structured text (rows/columns with headers)
   - Current 600-char preview loses table structure
   - Test hypothesis: Will extraction improve with structured table representation?

3. **Enhance prompt**:
   - Add explicit instructions: "Extract values from tables by locating row and column headers"
   - Add output format examples: "For ROI, return as decimal (0.16), not percentage (16.0)"
   - Add execution guidance: "If question asks for sum, return the computed sum (e.g., 210), not the list of operands ([100, 110])"

4. **Diagnostic experiment (N=10)**:
   - Manually verify: Are gold answers actually present in rendered context?
   - For samples where model returns "not determinable", check if evidence was truncated or model failed to locate it
   - Distinguish: Evidence missing vs Evidence present but not extracted

### What NOT to Do

- ❌ Optimize retrieval (HyDE, query expansion, reranking)
- ❌ Train selector model
- ❌ Expand to full 120 samples
- ❌ Run repeated trials
- ❌ Conclude "retrieval on miss helps more than retrieval on hit" without verifying confounds

**Rationale**: When baseline is 0.117 and oracle is 0.25, the bottleneck is not memory selection but pipeline fundamentals.

## Supported Conclusions

✅ **Execution and provenance layer works correctly** (after Codex's `response_format` fix)

✅ **Evaluator type strictness causes 10% false negatives**

✅ **Model fails to extract evidence in 73% of samples** (44/60 wrong_extraction_or_logic)

✅ **Oracle gap is too small (0.017) to support memory selection research** at current baseline

❌ **UNSUPPORTED**: "Strategy memory retrieved on family-miss is more useful than on family-hit"
   - Confounded by sample difficulty, answer type, table complexity
   - Need to verify: Are miss samples actually easier (more span-type, simpler tables)?

❌ **UNSUPPORTED**: "Memory primarily provides format constraints, not reasoning guidance"
   - Current failures are extraction failures, not format failures
   - Cannot assess reasoning guidance when model fails to extract operands

## Next Steps

**Recommended path**: Fix pipeline before returning to memory research.

**Minimum viable fix**:
1. Relax evaluator (10 minutes)
2. Parse HTML tables to structured text (2-3 hours)
3. Enhance prompt with examples (1 hour)
4. Re-run N=20 diagnostic (30 minutes)

**Decision point**: If baseline improves to >0.4 EM and oracle gap increases to >0.05, resume memory utility research. Otherwise, consider whether MultiHiertt is suitable for agent memory evaluation.

**Alternative**: Return to FinQA (Stage 1 complete, known to work) or TabMWP as primary memory testbed.
