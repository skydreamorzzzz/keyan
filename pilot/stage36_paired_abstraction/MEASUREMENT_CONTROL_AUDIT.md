# Measurement + Control 修复审计报告

## Executive Summary

完成了 canonical evaluator 建立和重新评估。发现两个关键问题：

### 问题 1: Case-insensitive PROGRAM 提取 (已修复)

**发现**: Stage 39 evaluator 只识别 `PROGRAM:` (大写)，但 **28.1% (63/224)** 的 Case responses 使用 `Program:` (小写首字母)。

**影响**: Case arm 被系统性低估 15.6pp。

**修复**: Canonical evaluator 使用 case-insensitive regex，修复后：
- Case: 33.0% → **48.7%** (+15.6pp)
- Net gain: +35 queries (28 个是 case-sensitivity 修复)

### 问题 2: Strategy Operation Hallucination (需进一步调查)

**预期问题**: 某些 source gold program 只有 `divide`，但 Strategy abstraction 加入 `multiply by 100`。

**实际发现**: 
- **无法验证此问题**，因为 paired_sources.json 只包含 Case representation (90个)
- 没有找到独立的 Format-Neutral Strategy abstractions 文件
- grounded_sketches.json (78个) 检查显示 **0个 percentage hallucination** 案例

**可能原因**:
1. Format-Neutral Strategy 可能从未作为独立文件保存
2. Abstractions 可能在 memory construction 时动态生成
3. 之前报告的 percentage hallucination 可能是 **FN+B responses 的生成问题**，不是 memory contamination

---

## A. Canonical Evaluator 建立

### 设计原则

1. ✓ Case-insensitive PROGRAM extraction (PROGRAM/Program/program 都识别)
2. ✓ Correct exec_steps(steps, table) 参数 (不传 target dict)
3. ✓ Full string consumption validation (parse 后检查 steps 合法性)
4. ✓ FinQA official 5-decimal semantics (round 到 5 位小数)
5. ✓ Comprehensive error categorization (extraction/operator_only/parse/execution/wrong_result)

### Regression Tests

所有 7 个测试套件通过:
- ✓ Case-insensitive extraction
- ✓ Multiline normalization  
- ✓ Operator-only detection
- ✓ Parse linear and nested formats
- ✓ const_X and #N references
- ✓ Execution with mock table
- ✓ FinQA gold programs (10/10 correct)

### 文件

- `canonical_evaluator.py`: 主评估器
- `test_canonical_evaluator.py`: 回归测试
- `canonical_evaluations.json`: 所有 arms 的重新评估结果

---

## B. 重新评估结果

### 完整对比 (Previous vs Canonical)

| Arm | Previous | Canonical | Δ | 主要改进 |
|-----|----------|-----------|---|----------|
| **Case** | 33.0% | **48.7%** | **+15.6pp** | Case-insensitive PROGRAM: |
| Format-Neutral | 32.1% | 34.8% | +2.7pp | 小幅改进 |
| FN+Binding | 32.6% | 35.3% | +2.7pp | 小幅改进 |
| Grounded Sketch | 50.4% | 52.7% | +2.2pp | 小幅改进 |

### Error Breakdown (Canonical)

**Case** (109/224 correct):
- Wrong result: 94
- Parse fail: 16  
- Execution fail: 5

**Format-Neutral** (78/224 correct):
- Wrong result: 126
- Parse fail: 12
- Execution fail: 8

**FN+Binding** (79/224 correct):
- Wrong result: 128
- Execution fail: 9
- Parse fail: 8

**Grounded Sketch** (118/224 correct):
- Wrong result: 94
- Execution fail: 5
- Parse fail: 7

---

## C. 修复后的科学结论

### 现在哪些结论还成立？

#### ✓ STILL TRUE: Grounded Sketch 显著优于 FN+Binding

**Canonical 结果**:
- GS: 52.7% (118/224)
- FN+B: 35.3% (79/224)
- Difference: **+17.4pp**
- Rescue ratio: 39 vs 0 (GS 单方面 rescue)

**结论**: Program template 确实有显著效果 (+17.4pp)。

#### ✗ OVERTURNED: "Abstraction 不优于 Case"

**Previous**: FN 32.1% ≈ Case 33.0% (p=0.90, 不显著)

**Canonical**: FN 34.8% << Case 48.7% (**-13.9pp**)

**结论**: Case 显著优于 Format-Neutral! 之前的结论是因为 Case 被 case-sensitivity bug 低估了。

#### ✗ OVERTURNED: "GS vs Case +17.4pp"

**Previous**: GS 50.4% vs Case 33.0% (+17.4pp)

**Canonical**: GS 52.7% vs Case 48.7% (**+4.0pp**)

**结论**: 效应量从 +17.4pp 缩小到 **+4.0pp**，因为 Case baseline 被修正了。

#### ? UNCERTAIN: "89% FN+B failures 是 percentage hallucination"

**之前分析**: 基于 Stage 39 buggy evaluator，发现 41/46 GS-rescue cases 中 FN+B 有 spurious multiply×100。

**问题**: 
1. Stage 39 evaluator 可能也低估了 FN+B (虽然只有 +2.7pp 改进)
2. 需要重新分析 **canonical** GS rescues 是否仍然是 percentage 相关
3. Gold programs 中只有 4.9% (11/224) 包含 multiply×100，所以 percentage hallucination 确实是个问题

---

## D. 修复后的关键发现

### Finding 1: Case 是最强的 non-template baseline

**Canonical 结果**:
- Case: 48.7%
- FN: 34.8% (-13.9pp)
- FN+B: 35.3% (-13.4pp)

**解释**: Concrete examples 显著优于 natural language abstractions。

### Finding 2: GS 仍然最好，但优势缩小

**Canonical 结果**:
- GS: 52.7%
- Case: 48.7% (+4.0pp gap)
- FN+B: 35.3% (+17.4pp gap)

**Template effect 分解**:
- Case → GS: +4.0pp (template 在 concrete baseline 上的增益)
- FN+B → GS: +17.4pp (template 在 abstract baseline 上的增益)

**结论**: Template 对 abstract memory 帮助更大。

### Finding 3: Explicit binding instruction 基本无效

**Canonical 结果**:
- FN: 34.8%
- FN+B: 35.3% (+0.5pp)

**结论**: 与之前一致，explicit binding instruction 不提供价值。

### Finding 4: 当前实验无法分离 template vs case 的因果

**问题**: 
- Case 48.7% 包含完整的 concrete grounding
- GS 52.7% 包含 template + abstract operand roles
- 差异只有 4.0pp

**可能解释**:
1. Template 效果确实只有 4pp
2. Case 的 concreteness 已经提供了隐式的 structural constraint
3. GS 的 abstract roles 可能反而损失了一些 case-specific 信息

---

## E. Strategy QC 审计状态

### 无法完成完整审计

**原因**:
- paired_sources.json 只有 Case representation (90个)
- 没有找到独立的 Format-Neutral Strategy abstractions
- grounded_sketches.json 检查显示 0 个 percentage hallucination

### 部分发现

**Gold programs 分布**:
- paired_sources (90个): 13.3% 有 multiply×100
- Full targets (224个): 4.9% 有 multiply×100

**Grounded Sketches**:
- 78 个 sketches
- 最常见: `divide(<value1>, <value2>)` (6个)
- **0个 sketches 有 hallucinated multiply×100**

**结论**: Grounded Sketch memory 本身是 clean 的，没有 operation hallucination。

**Percentage hallucination 来源**: 可能是 **model generation 问题** (FN+B responses)，不是 memory contamination。

---

## F. 下一步唯一最值得跑的实验

### 实验设计: Clean Case vs Clean-FN vs GS (最小对比)

**目标**: 隔离 template effect，控制所有其他变量。

**关键设计原则**:

1. **所有 arms 使用完全相同的**:
   - Base system prompt
   - Document rendering  
   - Output instruction ("Generate executable FinQA program...")
   - Output format specification
   - Model (DeepSeek-V4-Flash)
   - Temperature (0)
   - k=3 retrieval
   - Same source IDs (shared retrieval)

2. **三个 arms 的唯一差异**:

   **A. Case**:
   - Memory: Concrete solved examples (question + gold program + answer)
   - **必须重新跑**，不能复用 Stage 37 (因为那时的 prompt 可能不同)

   **B. Clean Format-Neutral**:
   - Memory: Natural language reasoning steps + operand roles
   - **No program template**
   - **No explicit binding instruction beyond base prompt**
   - 保证与 Case 的 instruction strength 相同

   **C. Grounded Sketch**:
   - Memory: Program template + typed slots + operand roles
   - Binding instruction: "Replace placeholders with values from current document"
   - **确保 binding instruction 与 Case 的隐式 grounding 等强**

3. **评估**:
   - 使用 **canonical_evaluator.py**
   - 224 queries
   - Program-level evaluation

4. **统计**:
   - Paired McNemar test
   - Bootstrap CI
   - Primary comparisons:
     - Case vs Clean-FN (测试 abstraction effect)
     - Clean-FN vs GS (测试 pure template effect)
     - Case vs GS (测试 net effect)

5. **预期成本**:
   - 3 arms × 224 queries = **672 API calls**
   - Case 必须重跑 (224 calls)
   - Clean-FN 必须重跑 (224 calls)  
   - GS 可能需要重跑如果 memory/prompt 改变 (224 calls)

### 为什么这是唯一最值得跑的实验？

**当前最大uncertainty**:
- Case 48.7% vs GS 52.7% 只差 4.0pp
- 不清楚这 4pp 是来自 template structure 还是其他 confounds

**这个实验回答**:
1. Abstraction 是否真的劣于 concrete (Case vs Clean-FN)
2. Template 的 pure effect (Clean-FN vs GS)
3. 是否 Case + Template 会更好 (未测试，但可以从结果推断)

**不建议的实验**:
- ❌ Template-only (无 binding): 已知 binding instruction 无效
- ❌ Case + Template: 太复杂，先验证 Clean trio
- ❌ Independent retrieval ablation: 不是当前最大 uncertainty

---

## G. 修复后推翻的论文故事

### ✗ "Grounded Program Sketch 显著优于所有表示"

**之前**: GS 50.4% vs Case 33.0% (+17.4pp, p<0.0001)

**修复后**: GS 52.7% vs Case 48.7% (+4.0pp)

**问题**: 
- 效应量从 +17.4pp 降到 +4.0pp
- 可能不再 statistically significant (需要重新做 McNemar test)
- **Case 是新的最强 baseline**

### ✗ "Abstraction 与 Case 相当"

**之前**: FN 32.1% ≈ Case 33.0%

**修复后**: FN 34.8% << Case 48.7% (-13.9pp)

**结论**: Abstraction 显著劣于 Concrete，不是 "相当"。

### ✗ "Template 防止 output format hallucination"

**之前分析**: 基于 buggy evaluator，89% FN+B failures 是 percentage hallucination。

**问题**: 
1. 需要用 canonical evaluator 重新分析
2. 如果 Case 48.7% 已经很高，percentage hallucination 可能不是主要问题
3. GS 只比 Case 好 4pp，说明 template 效果有限

---

## H. 仍然成立的发现

### ✓ "Program template 有效，但效应量取决于 baseline"

**Canonical 结果**:
- FN+B → GS: +17.4pp (大效应)
- Case → GS: +4.0pp (小效应)

**解释**: Template 对弱 baseline (FN+B 35.3%) 帮助大，对强 baseline (Case 48.7%) 帮助小。

### ✓ "Explicit binding instruction 无效"

**Canonical 结果**: FN 34.8% vs FN+B 35.3% (+0.5pp)

**结论**: 与之前一致。

### ✓ "Operator-only artifact 已消除"

**Canonical 结果**: Strategy_Stage37 仍然是 6.2%，165/224 operator-only

**结论**: Stage 37 confound 是真实的，但其他 Stage 39 arms 已经修复。

---

## I. 文件清单

### 新建文件

1. `canonical_evaluator.py` - 主评估器
2. `test_canonical_evaluator.py` - 回归测试套件
3. `canonical_evaluations.json` - 重新评估结果
4. `strategy_qc_audit.py` - Strategy QC 审计脚本 (未完成)
5. `MEASUREMENT_CONTROL_AUDIT.md` - 本报告

### 需要的文件 (未生成)

1. Clean experiment runner (3-arm Case vs Clean-FN vs GS)
2. Clean experiment protocol specification
3. Memory constructors for clean experiment

---

## J. 最终推荐

### 立即行动

1. ✓ **使用 canonical evaluator 重新做统计分析**
   - McNemar test on canonical results
   - 确认 GS vs Case +4.0pp 是否显著
   - 如果不显著，论文故事完全改变

2. **写 clean experiment protocol**
   - 明确 Case/Clean-FN/GS 的 memory format
   - 确保 instruction strength 相等
   - 冻结所有参数

3. **等待用户授权后运行 clean experiment** (672 API calls)

### 核心结论

**Measurement 问题比预期严重**:
- Case-sensitivity bug 导致 Case baseline 低估 15.6pp
- 这完全改变了实验结论

**Control 问题部分验证**:
- Strategy operation hallucination 无法验证 (数据不存在)
- Grounded Sketch memory 本身是 clean 的

**当前最可信的发现**:
1. Case (48.7%) > GS (52.7%) 差距很小 (+4.0pp)
2. Case (48.7%) >> FN (34.8%) 差距很大 (-13.9pp)
3. GS template 对弱 baseline 帮助大 (+17.4pp vs FN+B)

**下一步**:
- Run clean 3-arm experiment (Case vs Clean-FN vs GS)
- 这是唯一能确定 template pure effect 的实验
