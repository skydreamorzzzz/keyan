# Stage 36: 推理对齐诊断报告

**生成时间**: 2026-08-18  
**状态**: ✓ 诊断完成，准备进入 downstream experiment

---

## 一、数据构建总结

### 1.1 Paired Memory 构建

- **Source experiences**: 90 对 Case(E) + Strategy(E)
- **QC 通过率**: 78/90 (86.7%)
- **失败原因**: 12 个因年份片段泄漏（如演示文本中的 "20"）
- **结构多样性**:
  - 单步: 36 (40%)
  - 双步: 30 (33.3%)
  - 三步: 18 (20%)
  - 四步: 6 (6.7%)
- **操作类型**: divide, subtract, add, multiply, greater, table_average 等

### 1.2 Target Queries 选择

- **数量**: 30 个 FinQA dev 查询
- **采样策略**: 按首操作分层（top-6 families）
- **步数分布**:
  - 单步: 19 queries (63.3%)
  - 双步: 11 queries (36.7%)

### 1.3 Shared-Source Retrieval Protocol

- **检索方法**: Question-only embedding similarity (representation-neutral)
- **嵌入模型**: sentence-transformers/all-MiniLM-L6-v2 (384 dims)
- **Top-k**: 3 sources per target
- **总检索数**: 30 targets × 3 sources = 90 retrievals

---

## 二、语义相关性（Semantic Relevance）

**定义**: 基于问题文本嵌入的余弦相似度

### 统计分布

```
Mean:    0.551
Median:  0.536
Range:   [0.393, 0.785]
Std:     ~0.08
```

### 解读

- **中等相关性**: 平均 0.55 表示检索到的 sources 与 targets 在问题语义上中度相关
- **无精确匹配**: 最高相似度 0.785，无 train/dev 泄漏
- **合理分布**: 无异常高相似度（>0.9），避免 trivial retrieval

---

## 三、推理对齐（Reasoning Alignment）

**定义**: 基于 gold programs 的操作结构相似度（oracle diagnostic）

### 3.1 Operation Family Overlap (Jaccard)

集合相似度：`|ops_source ∩ ops_target| / |ops_source ∪ ops_target|`

```
Mean:    0.361
Median:  0.333
Range:   [0.000, 1.000]
```

**解读**: 平均约 1/3 的操作集合重叠

### 3.2 Operation Multiset Similarity (Cosine)

操作频率向量的余弦相似度

```
Mean:    0.409
Median:  0.382
Range:   [0.000, 1.000]
```

**解读**: 考虑操作重复后相似度略高（0.409 vs 0.361）

### 3.3 Structure Alignment (Normalized Edit Distance)

序列相似度：`1 - edit_distance / max_length`

```
Mean:    0.323
Median:  0.000
Range:   [0.000, 1.000]
```

**解读**: 
- 中位数为 0 说明多数检索的操作序列完全不同
- 平均 0.323 由少数高对齐检索拉高

### 3.4 多步 Target 的对齐度更高

```
Multi-step targets (n=33, 36.7%):
  Family Overlap:  0.444 (vs 整体 0.361)
  Multiset Sim:    0.524 (vs 整体 0.409)
  Structure Align: 0.359 (vs 整体 0.323)
```

**解读**: 复杂查询更容易与 sources 产生部分操作重叠

---

## 四、语义相似度 vs 推理对齐相关性

### Spearman 相关系数

```
Semantic Similarity vs:
  Operation Family Overlap:      ρ = 0.270
  Operation Multiset Similarity: ρ = 0.242
  Structure Alignment:           ρ = 0.234
```

### 关键发现 ⚠️

**语义相似度与推理对齐弱相关（ρ < 0.3）**

**含义**:
1. **正交维度**: 问题语义相似 ≠ 操作结构相似
2. **可测试性**: H5（"推理对齐比语义更接近效用"）可通过 downstream 实验验证
3. **非独立**: 0.24-0.27 的弱相关说明两者有轻微关联，但大部分方差独立

**示例场景**:
- **高语义/低推理对齐**: "计算 2015 年 ROA" vs "计算 2014 年 revenue growth" → 都是财务计算问题，但操作不同（divide vs subtract+divide）
- **低语义/高推理对齐**: "债务与资产比" vs "流动比率" → 问题用词不同，但都是 divide 操作

---

## 五、Source 复杂度分布（在检索结果中）

```
1 步: 31 (34.4%)
2 步: 43 (47.8%)
3 步: 11 (12.2%)
4 步: 5  (5.6%)
```

**关键**: 检索到的 sources 几乎一半是双步操作，提供了足够的结构多样性

---

## 六、实验控制验证

### ✓ 共享 Source IDs

每个 target 的 3 个 sources 在后续 4 arms 中完全一致：
- None arm: 无 memory
- Case arm: 使用 Case(E1), Case(E2), Case(E3)
- Strategy arm: 使用 Strategy(E1), Strategy(E2), Strategy(E3)
- Paired arm: 使用 Case(E1)+Strategy(E1), Case(E2)+Strategy(E2), Case(E3)+Strategy(E3)

### ✓ Representation-Neutral Retrieval

检索仅基于 question embedding，与 Case/Strategy 内容无关

### ✓ Train/Dev 分离

- Sources: FinQA train (78 from 6251)
- Targets: FinQA dev (30 from 883)
- 无精确问题重复（最高语义相似度 0.785）

---

## 七、决策门：是否继续 Downstream Experiment

### 通过标准

✓ **Paired memory 质量**: 86.7% QC 通过率  
✓ **Abstraction operator 稳定**: 仅轻微泄漏（年份片段），无结构损失/幻觉  
✓ **Retrieval protocol 实现**: 共享 source IDs 机制验证  
✓ **语义/推理对齐分布合理**: 无 trivial cases，提供足够方差  
✓ **弱相关性验证**: H5 可测试  

### 建议

**继续进入 downstream 4-arm pilot (30 queries)**

---

## 八、Downstream Experiment 设计要点

### 固定变量
- Model: DeepSeek-V3 (与 Stage 1-2 一致)
- Temperature: 0.7
- Top-k sources: 3
- Sample: 30 fixed targets (已选定)
- Evaluator: Exact match on executable answer
- Source selector: Question-only embedding (已实现)

### 唯一自变量
- **Memory representation**: None / Case / Strategy / Paired

### 观测指标
1. **Per-query EM**: 每个 query 的 4-arm 结果 (0/1)
2. **Transition patterns**: 
   - None 错 → Case 对 (concrete utility)
   - None 错 → Strategy 对 (abstract utility)
   - Case 对 → Strategy 错 (concrete 更优)
   - Case 错 → Strategy 对 (abstract 更优)
   - Paired 与 Case/Strategy 的增益/冲突
3. **Correlation with diagnostics**:
   - EM vs semantic similarity
   - EM vs reasoning alignment
   - Transition type vs operation family / complexity

### 分析原则
- **不设 pp 阈值**: 报告 transition counts，不强行判断显著性
- **定性模式优先**: 识别 H1-H5 的信号，不强求统计证明
- **保留负面结果**: 即使 4 arms 无差异，也记录并解释

---

## 九、H1-H5 可观测信号映射

| 假设 | 可观测信号 | 数据来源 |
|-----|----------|---------|
| H1: Concrete Case 依赖语义相似度 | Case arm EM 与 semantic similarity 相关性 > Strategy arm | 30-query results + alignment cache |
| H2: Strategy 在低语义/高推理对齐时有效 | Strategy 对/Case 错的 queries 有更高 reasoning alignment | Per-query transitions |
| H3: Strategy 改变负面干扰 | Case 错/Strategy 对的 queries 中，Case retrieval 的语义相似度分布 | Alignment cache |
| H4: Paired 互补 vs 冲突 | Paired 优于 max(Case, Strategy) vs 劣于 max | Per-query EM comparison |
| H5: 推理对齐更接近效用 | EM 与 reasoning alignment 相关性 > semantic similarity | Spearman on 90 retrievals × 4 arms |

---

## 十、输出文件清单

```
pilot/stage36_paired_abstraction/
├── paired_sources.json              # 90 source experiences (original)
├── cases_clean.json                 # 78 QC-passed Case(E)
├── strategies_clean.json            # 78 QC-passed Strategy(E)
├── qc_results.json                  # QC diagnostics
├── source_embeddings.npy            # 78 × 384 embedding matrix
├── target_queries.json              # 30 selected dev queries
├── retrieval_cache.json             # 30 targets → 90 retrievals mapping
├── reasoning_alignment.json         # 90 retrievals × alignment metrics
└── DIAGNOSTIC_REPORT.md             # This file
```

---

## 结论

**推理对齐诊断完成，实验准备就绪。**

下一步：实现 `downstream_experiment.py` 执行 4-arm pilot。
