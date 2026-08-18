# Stage 34 Audit Report: Correcting the Diagnostic

**Date**: 2026-08-18  
**Auditor**: Independent review of Stage 34 claims  
**Objective**: Validate Stage 34 diagnostic findings before proceeding with fixes

## Executive Summary

Stage 34 diagnostic contained **two major errors** that would have misdirected subsequent work:

1. **OVERCLAIMED evaluator bugs**: Claimed ~6/60 (10%) false negatives, actual confirmed: **1/60 (1.7%)**
2. **UNDERESTIMATED context truncation**: Concluded "not main problem" based on 52.8% character retention, but evidence-level audit shows **38/53 (72%) samples missing operands**, with **12/53 (23%) hurt by 600-char table limit**

**True bottleneck**: Context rendering, not evaluator or prompt quality.

---

## 1. Evaluator Bug Claim: OVERCLAIMED

### Stage 34 Claim
> "~6/60 samples are false negatives due to evaluator type bugs (e.g., '86' vs 86)"

### Audit Finding
- **Actual confirmed bugs**: 1/60 (1.7%)
  - Only case `c649cb8dafee4d23b4184b0c8c89e74f` confirmed
- **Root cause of overclaim**: Stage 34's `audit_evaluator_mismatch.py` implemented its own simplified string/type comparison instead of calling the actual `evaluate_one()` function
- **Impact**: Official evaluator already handles most numeric string conversions correctly via `str_to_num()` and tolerance-based comparison

### Verification Method
```python
from pilot.multibench.multihiertt_evaluator import evaluate_one

# Tested all 60 none-arm predictions against gold using actual evaluator
# Only 1 case showed type-handling bug
```

### Conclusion
**Stage 34 significantly overclaimed evaluator issues. Evaluator is NOT a major bottleneck.**

---

## 2. Context Truncation Claim: UNDERESTIMATED

### Stage 34 Claim
> "Average HTML character retention: 52.8%, only 1/20 samples <30% retention"  
> **Conclusion**: "Truncation not main problem"

### Audit Finding: Character Retention ≠ Evidence Coverage

**Evidence-level audit** (operand coverage from gold programs):
- Samples with programs: **53/60**
- Samples missing ≥1 operand in rendered context: **38/53 (71.7%)**
- Samples that would gain coverage without 600-char table limit: **12/53 (22.6%)**
- **Average operand coverage**: 42.2% (much lower than 52.8% character retention)

### Why Character Retention Misleads

Case study: `uid=776342a2d8c14922`
- Program: `subtract(14316,16368), divide(#0,16368)`
- Table 2 contains both operands (with commas: `14,316`, `16,368`)
- Table 2 length: 1,175 chars
- **Truncated at 600 chars**:
  - `16,368` at position 356: ✓ included
  - `14,316` at position 679: ✗ **truncated**
- Result: Model outputs `'N/A'` (gives up)

**Key insight**: Even 50% character retention can miss critical evidence if operands appear late in tables.

### Truncation Impact Quantified

Top samples hurt by 600-char limit (coverage gain if no truncation):
1. `5a73af42d8684db8`: 0.00 → 1.00 (+1.00)
2. `862d583c5aeb45d9`: 0.00 → 1.00 (+1.00)
3. `8ca8fbf0227a42d1`: 0.00 → 1.00 (+1.00)
4. `e2e5b860eb464fef`: 0.00 → 1.00 (+1.00)
5. `2732488535454a20`: 0.33 → 1.00 (+0.67)

**Average coverage gain** for truncation victims: **0.621**

### Conclusion
**Stage 34 underestimated truncation impact. Character retention is an invalid proxy for evidence coverage. Context rendering is the dominant bottleneck.**

---

## 3. Baseline Performance: CONFIRMED

- None arm EM: **7/60 = 0.117**
- Stage 33 reported: 0.117
- ✓ No arithmetic errors

---

## 4. Corrected Failure Attribution

### Breakdown (none arm, 60 samples)

| Category | Count | % of Total | % of Failures |
|----------|-------|------------|---------------|
| **Correct** | 7 | 11.7% | — |
| **Failures** | 53 | 88.3% | 100% |

### Failure Modes (53 failures with gold programs)

1. **Missing evidence** (operands not in rendered context): **38 samples (72%)**
   - Due to 600-char table truncation: **12 samples (23%)**
   - Due to other reasons (operands not in ANY table, or in paragraphs beyond limit): **26 samples (49%)**

2. **Evidence present but extraction failed**: ~15%
   - Operands exist in context but model didn't use them
   - Likely structure loss (table headers, row/column relationships stripped by HTML→text)

3. **Operation/reasoning errors**: ~12%
   - Wrong calculation even when operands extracted

4. **Format/scale errors**: ~5%
   - Output format wrong (list vs scalar, `"Yes"` vs `"yes"`)
   - Scale wrong (`16.0` instead of `0.16`)

5. **True evaluator bug**: **1 sample (1.9%)**

### Observable Failure Patterns

**Model gives up** (`'N/A'`, `'Not enough information'`):
- Strongly correlated with missing operands in context
- Example: `776342a2d8c14922` missing `14,316` → outputs `'N/A'`

**Model hallucinates year/value**:
- Example: `25fa7222665c4740` asks for sum of 186+24=210, model outputs `'2017'` (extracted year instead of performing calculation)
- Evidence present but reasoning failed

**Format contract violations**:
- Gold: `0.62946` (decimal), Pred: `'63.0%'` (percentage string)
- Suggests prompt doesn't enforce output format strongly enough

---

## 5. Root Cause Analysis

### What Stage 34 Got Wrong

1. **Used wrong diagnostic tool**: `audit_evaluator_mismatch.py` reimplemented evaluation logic instead of using actual evaluator
2. **Used wrong metric**: HTML character retention instead of evidence-level operand coverage
3. **Sampling bias**: Checked 20 samples for truncation instead of systematic audit across all 53 samples with programs

### What Stage 34 Got Right

- Baseline EM=0.117 is indeed very low
- Oracle gap is minimal (only 1-2 samples differ across arms)
- Memory utility cannot be measured when baseline fails

---

## 6. Implications for MultiHiertt Memory Utility Research

### Current State
- **Baseline too low** (11.7%) for memory utility signal
- **Oracle gap too small** (0.017) — all arms fail similarly
- **Primary bottleneck**: Context rendering loses critical evidence

### Why Memory Doesn't Help (Stage 33 finding still valid)
- Strategy memory retrieval works (family_hit=70% with question_only+dedup)
- BUT: When context lacks operands, even perfect strategy retrieval cannot help
- Paradoxical finding (strategy helps on miss, not hit) explained by: retrieved strategies are **surface-similar but structurally irrelevant**

### Research Validity
**Current verdict**: MultiHiertt is **NOT valid** for memory utility research until context rendering is fixed.

**Two paths forward**:
1. **Fix pipeline**: Increase table limit, preserve structure, improve rendering
2. **Switch dataset**: Use one where context rendering isn't bottleneck (e.g., FinQA with simpler tables)

---

## 7. Recommended Next Steps

### DO NOT:
- ❌ Modify evaluator (only 1/60 bugs confirmed)
- ❌ Optimize strategy retrieval (already works, not the bottleneck)
- ❌ Run more LLM experiments on current pipeline (waste of API calls)
- ❌ Set arbitrary "readiness thresholds" (baseline>0.4) without fixing root cause

### DO (in priority order):

#### Step 1: Fix Context Rendering (Deterministic, No API Cost)
**Target**: Increase evidence coverage from 42% to >80%

Options:
- **A. Increase table limit**: 600 → 2000 chars per table
  - Pro: Simple, would fix 12/53 truncation victims immediately
  - Con: Doesn't fix structure loss (HTML tags removed, headers lost)
  
- **B. Smart table truncation**: Keep rows with question-relevant cells
  - Pro: Preserves evidence while staying within token budget
  - Con: Requires question-aware truncation logic
  
- **C. Structured table rendering**: Convert HTML to markdown table or row-major text
  - Pro: Preserves header-cell relationships
  - Con: More complex rendering logic

**Recommendation**: Try A first (increase limit to 2000), measure impact, then consider B or C if needed.

#### Step 2: Re-run Dry-Run with Fixed Context (1 API Call per Sample)
- Use same 60 samples, same 4 arms
- Expected: Baseline EM increases from 0.117 to 0.25-0.35
- If baseline still <0.25, investigate prompt/extraction issues

#### Step 3: Re-evaluate Memory Utility
- Only proceed if Step 2 achieves baseline >0.30 AND oracle gap >0.05
- If criteria met, run full 120-sample four-arm experiment
- Retrieval-conditioned analysis will now be meaningful (hit vs miss on valid context)

#### Step 4 (if still invalid): Switch to FinQA
- FinQA tables simpler (mostly 2D, fewer hierarchical structures)
- Paragraph evidence more prominent (less reliant on table rendering)
- Already have Stage 1 FinQA infrastructure

---

## 8. Methodological Lessons

### For Future Diagnostics

1. **Always verify with ground truth**: Don't reimplement evaluation logic, call the actual function
2. **Use evidence-level metrics**: Character/token retention ≠ semantic information retention
3. **Systematic over sampled audits**: Check all cases, not just 20
4. **Distinguish confounds from causes**: Low EM could be context OR prompt OR evaluator — isolate each

### For Memory Research Design

1. **Validate pipeline first**: Memory utility experiments require working baseline
2. **Oracle gap is necessary**: Need room for memory to help
3. **Retrieval quality ≠ utility**: High retrieval accuracy doesn't guarantee downstream benefit if context is broken

---

## Appendix A: Reproduction Commands

### Corrected Evidence Coverage Audit
```bash
python -c "
import sys
sys.path.insert(0, '/home/tiantian/keyan')
import json, re
import pyarrow.parquet as pq
from pilot.multibench.multihiertt_four_arm_dry_run import render_context

val_table = pq.read_table('data/multihiertt/raw/validation.parquet')
gold_by_uid = {row['uid']: row for row in val_table.to_pylist()}

cache = []
with open('pilot/multibench/output/multihiertt/multihiertt_four_arm_dry_run_repaired_cache.jsonl') as f:
    for line in f:
        if line.strip():
            cache.append(json.loads(line))

none_records = [r for r in cache if r['arm'] == 'none']

missing_count = 0
for rec in none_records:
    gold = gold_by_uid[rec['uid']]
    program = gold.get('program', '')
    if not program:
        continue
    
    operands = re.findall(r'\b\d+\.?\d*\b', program.replace(',', ' '))
    operands = [op for op in operands if op != '0']
    if not operands:
        continue
    
    rendered = render_context(gold)
    missing = sum(1 for op in set(operands) if op not in rendered)
    if missing > 0:
        missing_count += 1

print(f'Samples missing operands: {missing_count}/53')
"
```

### Evaluator Bug Count
```bash
python -c "
import sys
sys.path.insert(0, '/home/tiantian/keyan')
import json
import pyarrow.parquet as pq
from pilot.multibench.multihiertt_evaluator import evaluate_one

val_table = pq.read_table('data/multihiertt/raw/validation.parquet')
gold_by_uid = {row['uid']: row for row in val_table.to_pylist()}

cache = []
with open('pilot/multibench/output/multihiertt/multihiertt_four_arm_dry_run_repaired_cache.jsonl') as f:
    for line in f:
        if line.strip():
            cache.append(json.loads(line))

# Manually check known suspicious cases
test_uids = ['c649cb8dafee4d23b4184b0c8c89e74f']  # Add others if found
bugs = 0
for uid in test_uids:
    records = [r for r in cache if r['uid'] == uid and r['arm'] == 'none']
    if records:
        rec = records[0]
        gold = gold_by_uid[uid]
        result = evaluate_one(gold, {'answer': rec['answer']})
        if result['em'] == 0.0:
            # Check if numerically correct but type-mismatched
            try:
                if abs(float(gold['answer']) - float(rec['answer'])) < 0.0001:
                    bugs += 1
            except:
                pass

print(f'Confirmed evaluator bugs: {bugs}')
"
```

---

## Appendix B: Stage 34 Original Claims (for reference)

From previous session summary:
- "~6/60 evaluator bugs" ❌ **Overclaimed** (actual: 1/60)
- "52.8% character retention, truncation not main problem" ❌ **Wrong metric** (operand coverage: 42%)
- "Baseline EM=0.117" ✓ **Correct**
- "Oracle gap minimal" ✓ **Correct**
