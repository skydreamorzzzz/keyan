# Stage 36 Runtime Provenance

**目的**: 冻结 downstream experiment 的完整 runtime 配置，确保可重现性

**日期**: 2026-08-18

---

## 1. Model Configuration

**Model**: DeepSeek-V3
- **API Endpoint**: via `pilot/llm.py` `call_once_with_metadata()`
- **Temperature**: 0.7
- **Max Tokens**: 2048
- **Timeout**: 180 seconds per call
- **Rate Limiting**: 0.5 seconds delay between calls

**Code Reference**: `pilot/stage36_paired_abstraction/downstream_experiment.py:221-227`

```python
result_data = call_once_with_metadata(
    messages,
    max_tokens=2048,
    temperature=0.7,
    timeout=180
)
time.sleep(CALL_DELAY)  # CALL_DELAY = 0.5
```

---

## 2. Prompt Template

**System Role**: Financial reasoning expert

**Prompt Structure** (`downstream_experiment.py:110-162`):

```
You are a financial reasoning expert. Answer the question using the provided context.

{memories}  # Empty for None arm, formatted memories for other arms

## Target Question

**Context (Pre-text)**:
{pre_text}

{table_str}  # If table exists

**Context (Post-text)**:
{post_text[:500]}...  # Truncated to 500 chars

**Question**: {question}

**Instructions**:
1. Understand what the question asks
2. Identify relevant values from the context
3. Determine the calculation steps needed
4. Execute the calculation
5. Provide the final numerical answer

Output format:
```
REASONING: [Your step-by-step reasoning]

PROGRAM: [Calculation in format: operation(arg1, arg2), ...]

ANSWER: [Final numerical answer]
```
```

**Memory Formatting**:

- **Case Memory** (`downstream_experiment.py:72-85`):
  ```
  ## Case Memory
  
  **Question**: {question}
  
  **Context**:
  {retrieval_text}
  
  **Solution**:
  Program: {program}
  Answer: {answer}
  Explanation: {explanation}
  ```

- **Strategy Memory** (`downstream_experiment.py:87-108`):
  ```
  ## Strategy Memory
  
  **Strategy Name**: {strategy_name}
  
  **Problem Pattern**: {problem_pattern}
  
  **Operation Sequence**: {operation_sequence}
  
  **Operand Roles**:
  {operand_roles}
  
  **Reasoning Steps**:
  {reasoning_steps}
  
  **Formula Template**: {formula}
  
  **Units Convention**: {units_convention}
  
  **Caveats**: {caveats}
  ```

- **Paired**: Both Case + Strategy for same source, concatenated

---

## 3. Answer Parser

**Function**: `parse_answer()` at `downstream_experiment.py:273-305`

**Logic**:
1. Search for line starting with "ANSWER:"
2. Extract content after "ANSWER:" prefix
3. Remove formatting: commas, dollar signs, percent signs
4. If "%" present, convert to decimal (divide by 100)
5. Parse as float
6. **Fallback**: Extract last number in response via regex `r'-?\d+\.?\d*'`

**Code**:
```python
def parse_answer(response: str) -> Any:
    lines = response.split("\n")
    for line in lines:
        if line.strip().startswith("ANSWER:"):
            answer_str = line.strip()[7:].strip()
            try:
                is_percentage = "%" in answer_str
                answer_str = answer_str.replace(",", "").replace("$", "").replace("%", "")
                if answer_str:
                    value = float(answer_str)
                    if is_percentage:
                        value = value / 100.0
                    return value
            except:
                return answer_str
    
    # Fallback: return last number
    import re
    numbers = re.findall(r'-?\d+\.?\d*', response)
    if numbers:
        try:
            return float(numbers[-1])
        except:
            pass
    
    return None
```

**Known Limitations**:
- Does NOT handle yes/no extraction from full sentences
- "No, the company spends less..." → entire string, not "no"
- "9198.333... (approximately 9198.33)" → last number is 9198.33 but may miss "..."
- These are **parser artifacts** that affect rescue/harm counts

---

## 4. Evaluator

**Function**: `evaluate_exact_match()` at `downstream_experiment.py:307-331`

**Logic**: Answer-only evaluation with 1% relative tolerance

**Code**:
```python
def evaluate_exact_match(predicted, gold, tolerance=0.01) -> bool:
    """Evaluate exact match with numerical tolerance.
    
    Note: Stage 36 uses answer-only evaluation (not program execution).
    This is less strict than official FinQA program execution evaluation.
    We use 1% relative tolerance for small numbers (<1) to handle precision loss
    from model text output (e.g., 0.0356 vs 0.03558).
    """
    if predicted is None or gold is None:
        return False
    
    try:
        pred_num = float(predicted)
        gold_num = float(gold)
        
        # Use relative tolerance for all non-zero numbers
        if abs(gold_num) > 0:
            return abs(pred_num - gold_num) / abs(gold_num) < tolerance
        else:
            # For zero, use absolute tolerance
            return abs(pred_num - gold_num) < tolerance
    
    except:
        # String comparison
        return str(predicted).strip().lower() == str(gold).strip().lower()
```

**Validity Boundary**:
- **NOT official FinQA evaluation**: Official uses `round(float(pred), 5) == gold` on executed programs
- **Answer-only**: Loses precision from intermediate calculations
- **1% tolerance**: Chosen to handle LLM text generation rounding (0.0356 vs 0.03558)
- **Documented limitation**: This is less strict than program execution evaluation

**Comparison to Official Evaluator** (`pilot/executor.py:268-287`):
```python
def official_normalize_result(result):
    # Used for program execution evaluation
    return round(float(result), 5)

def match_result(gold, pred):
    return official_normalize_result(gold) == official_normalize_result(pred)
```

---

## 5. Data Provenance

**Target Queries** (`target_queries.json`):
- 30 queries from FinQA dev set
- Sampled with operation family diversity
- No train/dev overlap (verified in Stage 36 retrieval)

**Source Memories**:
- `cases_clean.json`: 78 Case(E) memories (QC-passed from 90)
- `strategies_clean.json`: 78 Strategy(E) memories (QC-passed)
- QC failure rate: 13.3% (12/90, all due to leakage)

**Retrieval Cache** (`retrieval_cache.json`):
- 30 targets × 3 sources = 90 retrievals
- Shared source IDs across all arms (representation-neutral retrieval)
- Model: all-MiniLM-L6-v2 (384 dims)
- Metric: Cosine similarity on question-only embeddings
- Mean similarity: 0.551, Range: [0.393, 0.785]

**Reasoning Alignment** (`reasoning_alignment.json`):
- Oracle diagnostics using gold programs
- Metrics: Operation Family Overlap, Multiset Similarity, Structure Alignment
- Mean alignment: 0.32-0.41 (low to moderate)

---

## 6. Execution Metadata

**Date**: 2026-08-18

**Total API Calls**: 120 (30 queries × 4 arms)

**Estimated Runtime**: ~60 minutes (with 0.5s rate limiting)

**Execution Order**:
1. None arm (30 calls)
2. Case arm (30 calls)
3. Strategy arm (30 calls)
4. Paired arm (30 calls)

**Intermediate Saves**:
- Results saved after each arm completion
- Files: `results_none.json`, `results_case.json`, `results_strategy.json`, `results_paired.json`

**Final Outputs**:
- `experiment_results.json`: Aggregate statistics, transitions, correlations
- `rescue_harm_analysis.json`: Per-query rescue/harm patterns
- `STAGE36_FINAL_REPORT.md`: Full analysis report
- `RUNTIME_PROVENANCE.md`: This file

---

## 7. Reproducibility Checklist

To reproduce Stage 36 results:

1. **Environment**:
   - Python 3.x with scipy, numpy
   - Access to DeepSeek-V3 API via `pilot/llm.py`

2. **Data Files** (all in `pilot/stage36_paired_abstraction/`):
   - `cases_clean.json`
   - `strategies_clean.json`
   - `retrieval_cache.json`
   - `target_queries.json`
   - `reasoning_alignment.json`

3. **Code**:
   - `downstream_experiment.py` with frozen parser/evaluator

4. **Run Command**:
   ```bash
   python pilot/stage36_paired_abstraction/downstream_experiment.py
   ```

5. **Expected Outputs**:
   - 4 arm result files (JSON)
   - `experiment_results.json` with aggregate stats
   - Console output showing EM rates per arm

6. **Verification**:
   - None: 53.3% EM (16/30)
   - Case: 76.7% EM (23/30)
   - Strategy: 73.3% EM (22/30)
   - Paired: 76.7% EM (23/30)

---

## 8. Known Confounds and Artifacts

### 8.1 Parser Artifacts

**Yes/No Questions**:
- None outputs: "No, the company spends less..." (full sentence)
- Memory outputs: "no" (single word)
- Parser extracts ANSWER: line content as-is
- **Impact**: 5/8 rescues are format artifacts, not reasoning improvements

**Number Formatting**:
- None outputs: "9198.333... (approximately 9198.33)"
- Memory outputs: "9198.33"
- Parser regex extracts last number
- **Impact**: 1 rescue (LMT query) is format artifact

### 8.2 Evaluator Tolerance

**1% relative tolerance**:
- Masks small precision differences (0.0356 vs 0.03558)
- More lenient than official FinQA (5 decimal places)
- **Impact**: May count some borderline cases as correct

### 8.3 Shared-Source Protocol

**By design**: All arms use same source IDs per query

**Benefit**: Controls source selection confound

**Limitation**: Cannot observe Case vs Strategy optimal retrieval differences

---

## 9. Version Control

**Git Repository**: /home/tiantian/keyan

**Key Files**:
- `pilot/stage36_paired_abstraction/downstream_experiment.py`
- `pilot/stage36_paired_abstraction/STAGE36_FINAL_REPORT.md`
- `pilot/stage36_paired_abstraction/RUNTIME_PROVENANCE.md`

**No Git Commits Made**: Per user instruction "不要执行 Git 写操作"

**Recommendation**: Commit these files to preserve Stage 36 state before future changes

---

**Provenance Frozen**: 2026-08-18  
**Experiment Status**: Complete, results valid with documented limitations
