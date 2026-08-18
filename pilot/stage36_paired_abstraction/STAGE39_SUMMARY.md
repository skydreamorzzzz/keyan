# Stage 39 完整验证总结

## 实验完成情况

✓ **672 API calls 完成** (3 arms × 224 queries)
✓ **程序级评估完成** (所有响应已执行并验证)
✓ **统计分析完成** (McNemar检验 + Bootstrap CI)
✓ **GO/NO-GO决策完成** (应用预设规则)

---

## 核心发现

### 1. Format-Neutral + Binding = Grounded Sketch

**关键结果**: 
- Format-Neutral+Binding: 40.6% 准确率
- Grounded Sketch: 40.6% 准确率
- 差异: 0.0pp (95% CI: [-2.7, 2.7], p=1.0)

**结论**: Program template (程序模板 + typed slots) **不提供额外价值**

### 2. 抽象表示显著优于具体案例

**Format-Neutral vs Case**:
- 准确率差异: +8.5pp (95% CI: [3.6, 13.8])
- McNemar p值: 0.0019 ✓ **显著 (α=0.0125)**
- Rescue比例: FN=27, Case=8

**Grounded Sketch vs Case**:
- 准确率差异: +9.4pp (95% CI: [4.5, 14.3])
- McNemar p值: 0.0003 ✓ **显著 (α=0.0125)**
- Rescue比例: GS=27, Case=6

### 3. Explicit Binding Instruction 效果微弱

**Format-Neutral+Binding vs Format-Neutral**:
- 准确率差异: +0.9pp (95% CI: [-2.2, 4.0])
- McNemar p值: 0.7744 ✗ **不显著**
- 方向正确但效应量小

**可能原因**:
- Base Format-Neutral 的 operand role descriptions 已隐式引导 binding
- Binding instruction 设计不够强或未被模型充分利用
- 效应量确实很小，需要更大样本才能检测

### 4. Stage 37 Confound 确认并修复

| 指标 | Stage 37 Strategy (有confound) | Stage 39 Format-Neutral (无confound) | 改善 |
|-----|-------------------------------|--------------------------------------|-----|
| 准确率 | 6.2% | 39.7% | +33.5pp |
| 可执行率 | 21.0% | 88.8% | +67.8pp |
| Operator-only率 | 75.9% | 0.0% | -75.9pp |

**验证**: Prompt format confound 是真实且灾难性的，消除后恢复 33.5pp 准确率。

---

## GO/NO-GO 决策: Scenario B (修正版)

### 应用预设规则

**Scenario A (GS Method Paper)**: ✗ 失败
- GS > FN+B + 3.0pp? → NO (0.0pp)

**Scenario B (Binding Dominates)**: ✓ 部分成立
- FN+B ≈ GS? → YES (0.0pp, p=1.0) ✓
- FN+B > FN + 5.0pp? → NO (+0.9pp, 不显著) ✗
- FN+B > Case + 3.0pp? → YES (+9.4pp, p<0.001) ✓

**Scenario C (Execution Only)**: ✗ 失败
**Scenario D (Abstraction Fails)**: ✗ 失败

### 最终判定

**Scenario B (修正解读)**:
1. **GS = FN+B** 证明 program template 无独立价值
2. **FN+B ≈ FN** 说明 explicit binding instruction 效果微弱
3. **FN > Case** 证明清洁抽象表示有效
4. **主要收益来自**: 消除 confound + 自然语言 reasoning pattern

---

## 推荐论文故事线

### 标题
**"Prompt Design for Executable Program Synthesis from Abstract Experience Memory"**

或

**"Beyond Prompt Format Artifacts: Clean Abstraction for Program Synthesis"**

### 核心贡献

1. **方法论贡献**: Prompt format confound 识别与消除
   - 展示 prompt rendering 如何主导实验结果
   - 提供 format-neutral design 指南
   - 验证修复效果 (+33.5pp)

2. **表示贡献**: 自然语言抽象策略优于具体案例
   - Format-Neutral Strategy: +8.5pp vs Case (p=0.002)
   - 无需复杂 program template 或 typed slots
   - Operand role descriptions 已足够引导 binding

3. **设计原则**: 清晰自然语言指令 > 形式化模板结构
   - Program template 不提供额外准确率
   - Explicit binding instruction 效果微弱（可能已隐式存在）
   - 简单有效原则：Format-Neutral 足够好

### 诚实边界

**承认限制**:
- Explicit binding instruction 单独效果不显著
- Grounded Sketch 增加可执行率 +1.3pp，但实际意义有限
- 结果特定于 FinQA domain + DeepSeek-V4-Flash

**不过度包装**:
- 不声称 "Grounded Program Sketch 是新方法"
- 不声称 "解决了 abstraction-grounding trade-off"
- 聚焦真实贡献：confound 识别 + clean prompt design

---

## 与 Stage 38 Pilot 对比

| Arm | Pilot 准确率 (n=40) | Full 准确率 (n=224) | Bias |
|-----|---------------------|---------------------|------|
| Case | 52.5% | 31.2% | +21.3pp |
| Format-Neutral | 57.5% | 39.7% | +17.8pp |
| Grounded Sketch | 72.5% | 40.6% | +31.9pp |

**验证**: Pilot sample enriched，Full 224 提供无偏估计。Stage 38 的定性结论仍然成立（GS=FN+B，均优于Case），但定量估计大幅下调。

---

## 文件清单

### 数据文件
- `results_case_expanded.json` (Stage 37复用, 224 responses)
- `results_format_neutral_full224.json` (新运行, 224 responses)
- `results_format_neutral_binding_full224.json` (新运行, 224 responses)
- `results_grounded_sketch_full224.json` (新运行, 224 responses)

### 评估结果
- `stage39_full224_evaluations.json` (程序级评估，含准确率/可执行率)
- `stage39_statistical_results.json` (McNemar检验, Bootstrap CI, rescue分析)

### 报告
- `STAGE39_FULL224_RESULTS.md` (完整结果报告，英文)
- `STAGE39_SUMMARY.md` (本文件，中文总结)

### 代码
- `stage39_prompts.py` (冻结的prompt protocol)
- `stage39_memory_constructors.py` (各arm的memory构造函数)
- `stage39_execute_full224.py` (实验执行脚本)
- `stage39_evaluator.py` (程序级评估器)
- `stage39_statistical_analysis.py` (统计检验)

---

## 下一步行动

### 立即行动
1. ✓ 阅读 `STAGE39_FULL224_RESULTS.md` 获取完整英文报告
2. ✓ 检查 `stage39_statistical_results.json` 查看详细统计结果
3. ✓ 决定论文撰写方向（推荐：Prompt Design / Confound Elimination）

### 论文撰写
1. **Introduction**: Motivation (agent memory × program synthesis), confound发现
2. **Related Work**: CBR, program synthesis, prompt engineering
3. **Method**: 
   - Stage 37 confound识别
   - Format-neutral design
   - 三种表示对比 (Case, FN, FN+B, GS)
4. **Experiments**: 
   - FinQA 224 queries
   - 程序级评估 (不仅answer matching)
   - Paired statistical tests
5. **Results**: 
   - Confound修复 +33.5pp
   - FN vs Case +8.5pp
   - GS = FN+B (template无效)
6. **Discussion**: 
   - 为什么binding instruction效果微弱
   - 自然语言描述的隐式引导
   - Prompt engineering > 形式化方法
7. **Conclusion**: Careful prompt design matters more than representation complexity

### 未来工作
1. 测试其他领域 (semantic parsing, code generation)
2. 研究更强的 explicit binding mechanism
3. 分析 unique rescue patterns
4. 探索 Case + Abstract 混合策略

---

## 实验卫生准则 (从本研究学到的)

1. **总是检查 prompt format artifacts** 再归因于表示差异
2. **在完整数据集验证**，不仅依赖 enriched pilot
3. **配对统计检验** 用于匹配样本
4. **预先承诺 GO/NO-GO 规则** 不事后改标准
5. **愿意拒绝自己的假设** 当数据不支持时
6. **诚实报告限制** 不过度包装方法
7. **区分 FACT / interpretation / hypothesis** 明确证据强度

---

## 最终裁决

**Stage 39 验证了清洁抽象表示有效，但 program template 不提供额外价值。**

**故事是 prompt engineering 和 confound elimination，不是新表示方法。**

**推荐发表角度**: "Methodological contribution: 识别并消除 prompt format confound" + "Empirical contribution: 自然语言抽象策略在 financial QA 中的有效性"

---

**报告生成时间**: 2026-08-18  
**实验完成**: Stage 36 → Stage 37 → Stage 38 Pilot → Stage 39 Full-224  
**总API调用**: 672 (Stage 39) + 80 (Stage 38 Pilot) = 752 calls  
**仓库**: https://github.com/skydreamorzzzz/keyan
