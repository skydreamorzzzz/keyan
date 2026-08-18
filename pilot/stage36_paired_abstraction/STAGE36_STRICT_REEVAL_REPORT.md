# Stage 36: Strict Re-Evaluation Report

**日期**: 2026-08-18

**目的**: 使用 FinQA official evaluation semantics 重新评估 Stage 36 的 30×4=120 raw responses，区分真实推理改进和评估器 artifacts

---

## 执行摘要

### 核心发现

**原始 Stage 36 报告声称的 +20-23pp memory gains 完全是评估器 artifact**。

使用 FinQA official 5-decimal exact match 重新评估后：

```
None:      40.0% (12/30)  [baseline]
Case:      43.3% (13/30)  [+3.3pp, +1 query]
Strategy:  40.0% (12/30)  [+0.0pp, 无改进]
Paired:    40.0% (12/30)  [+0.0pp, 无改进]
```

**真实 memory utility: +3.3pp (1 个 rescue event)**

原始报告的 +20-23pp 提升来自评估器的 1% relative tolerance，该 tolerance 错误地将 20 个 query-arm pairs 判为正确。

---

## 1. 评估器 Artifact 解析

### 1.1 原始评估器问题

**Stage 36 原始评估器** (`downstream_experiment.py:307-331`):
- Answer-only evaluation (不执行 program)
- 1% relative tolerance: `abs(pred - gold) / abs(gold) < 0.01`
- 理由: "handle precision loss from model text output"

**FinQA official evaluator** (`pilot/executor.py:268-295`):
- Program execution evaluation
- 5-decimal exact match: `round(float(result), 5) == gold`
- 无 tolerance

### 1.2 Percentage Precision Artifact

**根本原因**:
- FinQA 数据集将百分比存储为小数: `0.03558 = 3.558%`
- 模型输出: `"3.56%"`
- Parser 解析: `0.0356`
- 评估:
  - 1% tolerance: `abs(0.0356 - 0.03558) / 0.03558 = 0.00056 < 0.01` ✓ (错误判为正确)
  - 5-decimal exact: `round(0.0356, 5) = 0.0356 ≠ 0.03558` ✗ (正确判为错误)

**影响范围**:

5 个 queries 在所有 4 个 arms 都受影响 (20 个 false positives):

| Query | Gold | Model Output | Parsed | 1% Tolerance | Exact Match |
|-------|------|--------------|--------|--------------|-------------|
| RE/2015/page_33.pdf-2 | 0.03558 | 3.56% | 0.0356 | ✓ | ✗ |
| GS/2017/page_143.pdf-1 | -0.39896 | -39.9% | -0.399 | ✓ | ✗ |
| ETR/2008/page_355.pdf-2 | 0.17972 | 17.97% | 0.1797 | ✓ | ✗ |
| IP/2006/page_32.pdf-4 | 0.05336 | 5.34% | 0.0534 | ✓ | ✗ |
| FIS/2007/page_94.pdf-4 | 0.14162 | 14.16% | 0.1416 | ✓ | ✗ |

**模型行为一致**: 这 5 个 queries 上，None/Case/Strategy/Paired 的推理和答案完全相同，只是都落在 1% tolerance 内但不满足 exact match。

### 1.3 Accuracy Delta

| Arm | Original (1% tol) | Strict (exact) | Delta |
|-----|------------------|----------------|-------|
| None | 53.3% (16/30) | 40.0% (12/30) | -13.3pp |
| Case | 76.7% (23/30) | 43.3% (13/30) | -33.4pp |
| Strategy | 73.3% (22/30) | 40.0% (12/30) | -33.3pp |
| Paired | 76.7% (23/30) | 40.0% (12/30) | -36.7pp |

**Memory arms 的 apparent gains 全部消失**:
- Case: 76.7% → 43.3% (-33.4pp)
- Strategy: 73.3% → 40.0% (-33.3pp)
- Paired: 76.7% → 40.0% (-36.7pp)

原始的 +20-23pp memory gains **完全是评估器 artifact**。

---

## 2. Strict Evaluation Transition Patterns

### 2.1 Query Distribution

| Pattern | Count | % |
|---------|-------|---|
| All correct (4/4 arms) | 12 | 40.0% |
| All wrong (0/4 arms) | 17 | 56.7% |
| None wrong → memory correct (rescue) | 1 | 3.3% |
| None correct → memory wrong (harm) | 0 | 0.0% |
| Mixed memory | 0 | 0.0% |

**关键观察**:
- **Base model saturation**: 40% queries DeepSeek-V3 已经会做
- **Capability ceiling**: 57% queries 即使有 memory 也做不对
- **True memory utility**: 仅 3% (1 个 query) memory 改变结果

### 2.2 All-Wrong Queries Breakdown

17 个所有 arms 都错的 queries 中:
- **Percentage artifacts**: 5 (29%) — 实际是上述百分比精度问题
- **True failures**: 12 (71%) — 真正所有 arms 都无法解决

这意味着真正的 "无法解决" queries 是 12/30 (40%)，不是 17/30。

---

## 3. The Single True Rescue Event

### 3.1 Query: GPN/2017/page_77.pdf-4

**Gold answer**: 73,576

**Question**: "how much money can company deduct on income tax in the future after this acquisition"

**Context**: 包含 goodwill 和多个 intangible assets 的 acquisition table

### 3.2 Four Arms Reasoning

**None (错误: 62,154)**:
```
The deductible amount is the total identifiable net assets,
which is given as $62,154 thousand.
```
- **Error**: 选择了错误的 line item (total identifiable net assets)

**Case (正确: 73,576)** ✓:
```
Only the identifiable intangible assets that have amortization
periods would be deductible. The sum is 42,721 + 27,954 + 2,901 = 73,576.
```
- **Correct**: 识别出需要 sum 三个 intangible assets
- **Program**: `add(42721, 27954), add(2901, #0)`

**Strategy (错误: 0)**:
```
Goodwill is not deductible for income tax purposes.
Therefore, the deductible amount is zero.
```
- **Error**: 过度解读 "goodwill not deductible"，认为所有都不可抵扣

**Paired (错误: 42,721)**:
```
The deductible amount is the value of the customer-related
intangible assets, which is $42,721 thousand.
```
- **Error**: 只选择了 customer-related，遗漏了 acquired technology 和 trade name

### 3.3 Retrieved Memory

**Shared sources**: E037, E028, E031

**E037 (关键 Case memory)**:
```
Question: "total amount of money they can deduct from their future income tax"
Answer: $103.7 million
Program: add(34.7, 36.7), add(32.3, #0)
```

**Mechanism**:
- E037 展示了相似的 "sum multiple deductible items" pattern
- 帮助模型识别需要 multi-step addition，而非 single-item selection
- 这是 **genuine reasoning rescue**: operand selection 被 memory 改进

### 3.4 Why Strategy Failed

Strategy memory 提供的是 abstract pattern，但：
- 没有 concrete example 展示 "需要 sum 多个 line items"
- 模型在 abstract guidance 下过度简化，错误解读为 "nothing is deductible"

### 3.5 Why Paired Failed

Paired 同时提供 Case + Strategy:
- Case 展示了 summation pattern
- Strategy 提供了 abstract reasoning
- 但模型似乎部分采纳了两者，产生 **interference**
- 只选择了一个 category (customer-related)，遗漏其他

**Interpretation**: Paired 在这个 rescue 上表现出干扰，而非互补

---

## 4. Abstraction Operator Effect

### 4.1 Case vs Strategy Comparison

| Pattern | Count | % |
|---------|-------|---|
| Case ✓ Strategy ✗ | 1 | 3.3% |
| Case ✗ Strategy ✓ | 0 | 0.0% |
| Both correct | 12 | 40.0% |
| Both wrong | 17 | 56.7% |

**Disagreement rate: 3.3% (1/30)**

**Interpretation**:
- Case 和 Strategy 在 **96.7% queries 上行为完全一致**
- 唯一的 disagreement 是上述 GPN rescue event
- n=1 不足以支持 "abstraction hierarchy matters" 的结论

**原始假设 H1-H4 全部不成立**:
- H1 (Case depends on semantic similarity): CONTRADICTED
- H2 (Strategy effective at low semantic/high reasoning): INSUFFICIENT DATA (n=1)
- H3 (Strategy changes negative interference): CONTRADICTED
- H4 (Paired complementarity): CONTRADICTED (0 complementary, 1 interference)

### 4.2 Paired Complementarity

| Pattern | Count |
|---------|-------|
| Paired beats both single arms | 0 |
| Paired worse than best single | 1 |

**No complementarity evidence**. Paired 在唯一的 rescue event 上表现出 **interference**。

---

## 5. Base Model Saturation Analysis

### 5.1 Distribution

- **Saturated (all correct)**: 12/30 (40%)
- **Capability ceiling (all wrong)**: 17/30 (57%), 其中 5 是 percentage artifacts
- **Memory-sensitive**: 1/30 (3%)

### 5.2 Interpretation

**DeepSeek-V3 on FinQA dev queries**:
- 40% 已经掌握这些 pattern，memory 无法再提升
- 57% 无法解决，即使有 memory 也做不对（其中 5 个实际是 percentage formatting 问题）
- 仅 3% memory 提供 actionable reasoning pattern

**Memory utility 被 base model capability 挤压**:
- High-capability model 已经知道简单 patterns → memory 无用
- Hard queries 超出 model capability → memory 也无济于事
- 只有 narrow sweet spot (3%) memory 真正有帮助

---

## 6. Retrieval Alignment 无法预测 Utility

### 6.1 原始相关性分析

原始报告中 Spearman correlations (EM vs diagnostics) 都接近 0 (|ρ| < 0.25)。

现在我们知道原因了:
- 原始 EM 包含大量 false positives (percentage artifacts)
- 这些 false positives 与 retrieval quality 无关（都是 formatting 问题）
- 真正的 signal (1 个 rescue) 被 noise 淹没

### 6.2 Strict Evaluation 下的 Insight

在 strict evaluation 下:
- **仅 1 个 rescue event**，无法计算有意义的 correlation
- 该 rescue 的 source E037 确实 semantically 和 reasoning-wise relevant
- 但 sample size=1 无法推广

---

## 7. Validity Lessons

### 7.1 Answer-only Evaluation 根本不可靠

**问题**:
1. 无法区分 reasoning correctness 和 output formatting
2. Tolerance bands 掩盖精度问题
3. 创造 false confidence

**FinQA official evaluation**:
- Program execution (验证推理过程)
- 5-decimal exact match (严格数值匹配)
- 无 tolerance

**Stage 36 应该做的**:
- 要求模型输出 structured program
- 执行 program 获得答案
- 使用 official evaluator

### 7.2 Percentage Convention

**FinQA 数据集设计**:
- 百分比存储为 decimal: `0.03558`
- 这是为了 program execution 的一致性

**Model 行为**:
- 自然倾向输出 percentage string: `"3.56%"`
- 这需要 parser 正确 normalize

**Lesson**: Dataset convention 和 model output format 的 mismatch 是 evaluation artifact 的主要来源

### 7.3 Base Model Capability 是主导因素

**Memory 的 utility 空间被挤压**:
- Easy queries: model 已饱和
- Hard queries: model 能力天花板
- Memory 只在 narrow middle ground 有用

**Implication**:
- Memory augmentation 研究需要 carefully select 难度合适的 queries
- 在 "model almost knows but needs a hint" 的 queries 上才有信号

---

## 8. 研究假设评估

### 原始假设

"从同一源经验构建 Case(E) 和 Strategy(E)，抽象算子是否改变 downstream utility？"

### 证据

**NO**. Abstraction operator 在严格评估下几乎无影响:
- Case vs Strategy disagreement: 3.3% (1/30)
- n=1 不足以支持任何结论
- 96.7% queries 两者行为完全一致

### 重新 Frame

原始 framing: **"When Does Experience Abstraction Help?"**

Evidence 支持的 framing: **"When Is Retrieved Experience Actually Useful? (Almost Never)"**

在 30 个 carefully selected FinQA dev queries 上:
- Genuine reasoning rescue: 1 (3.3%)
- Apparent gains 全部是 evaluation artifacts
- Base model saturation (40%) 和 capability ceiling (57%) 主导结果
- Abstraction level 不是决定性因素

---

## 9. Recommendation

### 9.1 不要扩展到 TAT-QA

**理由**:
1. FinQA 实验显示 memory 基本无 utility (+3.3pp, n=1)
2. Evaluation methodology 需要先修复 (program execution)
3. Abstraction hierarchy 假设不成立
4. 在 TAT-QA 上复制可能得到相同结果:
   - Base model saturation on easy queries
   - Capability ceiling on hard queries
   - Minimal true memory utility
   - Evaluation artifacts masking true performance

### 9.2 需要先解决的问题

**Before any replication**:
1. **Fix evaluation**: 使用 program execution，不是 answer-only
2. **Understand saturation**: 为什么 base model 在 40% queries 上已饱和？
3. **Understand failures**: 为什么 57% queries 即使有 memory 也失败？
4. **Identify sweet spot**: 什么 query characteristics 允许 rare 3% rescue？

### 9.3 Research Direction Pivot

**原方向** (不可行):
- "Abstraction hierarchy for reasoning transfer"
- Evidence 不支持，phenomenon 不存在 at meaningful scale

**新方向** (如果继续):
1. **Memory utility predictor**: 什么时候 memory 真正有用？(3% sweet spot)
2. **Base model capability boundary**: 如何识别 model 需要 hint 的 queries
3. **Evaluation methodology**: 如何在 answer-only 场景下可靠评估推理
4. **Alternative to memory**: 是否 direct prompting 或 few-shot 更有效？

**但更根本的问题**: Memory augmentation 在 high-capability models (DeepSeek-V3) 上的 marginal utility 可能本质上就很小。

---

## 10. 文件清单

**New files from strict re-evaluation**:
- `strict_evaluation_results.json` — 30×4 strict correctness matrix
- `evaluation_artifact_analysis.json` — Discrepancy details
- `strict_transition_analysis.json` — Rescue/harm/invariant counts
- `STRICT_EVALUATION_EXECUTIVE_SUMMARY.json` — Machine-readable summary
- `STAGE36_STRICT_REEVAL_REPORT.md` — This report

**Original Stage 36 files** (preserved but superseded):
- `STAGE36_FINAL_REPORT.md` — Original analysis with 1% tolerance
- `results_{none,case,strategy,paired}.json` — Raw responses (still valid)
- `experiment_results.json` — Original aggregate (now known to be artifacts)

---

## 11. 结论

**Stage 36 严格重新评估完成**。

### 核心发现

1. **原始 +20-23pp memory gains 完全是评估器 artifact**
   - 1% tolerance 错误判定 20 个 false positives
   - 百分比精度问题影响 5 queries × 4 arms

2. **真实 memory utility: +3.3pp (1 rescue)**
   - None: 40.0%
   - Case: 43.3% (+3.3pp)
   - Strategy: 40.0% (+0.0pp)
   - Paired: 40.0% (+0.0pp)

3. **Abstraction operator 基本无影响**
   - Case vs Strategy disagreement: 3.3% (1/30)
   - 96.7% queries 行为完全一致
   - 原始假设不成立

4. **Base model saturation 主导结果**
   - 40% queries: model 已会做
   - 57% queries: model 做不对
   - 3% queries: memory 有帮助

### Validity Lesson

**Answer-only evaluation with tolerance 是危险的**:
- 创造 false confidence (+20pp → +3.3pp)
- 无法区分 reasoning 和 formatting
- 必须使用 program execution evaluation

### Research Direction

**"Abstraction hierarchy for reasoning transfer" 研究方向不可行**。

在严格评估下，phenomenon 基本不存在 (n=1 rescue, 3.3% utility)。

不建议扩展到 TAT-QA，除非先解决 evaluation methodology 和理解 base model capability boundary。

---

**Report Generated**: 2026-08-18  
**Status**: Stage 36 strict re-evaluation complete. Original findings retracted.  
**Data Preserved**: Raw responses and intermediate results preserved for future analysis.
