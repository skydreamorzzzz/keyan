# Stage 36: Paired Abstraction Feasibility Study

**研究问题**: 如何从同一个已解决经验 E 构建 Case(E) 和 Strategy(E)，从而隔离抽象算子效应？

**实验设计**: 最小对照实验，唯一自变量为 memory representation (None/Case/Strategy/Paired)

---

## 1. Paired Memory 构建

### 1.1 Source Experience 选择

**FACT**:
- 从 FinQA train 选择 90 个 diverse source experiences
- 使用结构化分层采样（按 program structure）
- 保证操作家族多样性

**数据**:
- 最终通过 QC 的 pairs: 78 对
- source_experience_id: E001-E090
- 文件: `paired_sources.json`, `cases_clean.json`, `strategies_clean.json`

---

## 2. Abstraction Operator QC

### 2.1 QC 维度

1. **Leakage**: 是否泄露公司名、年份、具体数值
2. **Structural Preservation**: 是否保留操作序列
3. **Hallucination**: 是否添加源中不存在的操作
4. **Degeneracy**: 是否退化为空模板

### 2.2 QC 结果

**FACT**:
- 总策略数: 90
- 通过所有检查: 78 (86.7%)
- 失败: 12 (13.3%)
  - 全部失败原因: Leakage（年份片段如 "20"）
  - 无 structural preservation / hallucination / degeneracy 失败

**INTERPRETATION**:
- 抽象算子在大部分情况下稳定
- 失败案例为边缘情况（demonstrative text 中的年份片段）
- 构建质量足以支持 downstream feasibility study

**决策**: ✓ 继续进行 retrieval 和 downstream 实验

---

## 3. Shared-Source Retrieval 协议

### 3.1 设计原则

**关键控制**: 所有 representation arms 必须使用 **完全相同** 的 source experience IDs

**方法**: Representation-neutral retrieval
- 使用 question-only embedding similarity
- Model: all-MiniLM-L6-v2 (384 dims)
- Metric: Cosine similarity

### 3.2 Target 选择

**FACT**:
- 从 FinQA dev 选择 30 diverse target queries
- 使用操作家族分层采样
- 保证与 train 没有重叠

### 3.3 Retrieval 结果

**FACT** (Semantic Relevance):
- Top-3 retrieval per target (30 × 3 = 90 retrievals)
- Similarity statistics:
  - Mean: 0.551
  - Median: 0.536
  - Range: [0.393, 0.785]
- Exact question matches: 0 / 90 (无 train/dev leakage)

**文件**: `retrieval_cache.json`, `target_queries.json`, `source_embeddings.npy`

---

## 4. Reasoning Alignment Diagnostic

### 4.1 方法

**Oracle diagnostic** 使用 gold programs 测量:
1. **Operation Family Overlap**: Jaccard similarity of operation sets
2. **Operation Multiset Similarity**: Cosine similarity of operation frequency vectors
3. **Structure Alignment**: Normalized Levenshtein edit distance

### 4.2 结果

**FACT** (Reasoning Alignment):
- Operation Family Overlap:
  - Mean: 0.361
  - Median: 0.333
- Operation Multiset Similarity:
  - Mean: 0.409
  - Median: 0.382
- Structure Alignment:
  - Mean: 0.323
  - Median: 0.000 (许多完全不同的序列)

**FACT** (Correlation):
- Semantic Similarity vs Operation Family Overlap: ρ = 0.234
- Semantic Similarity vs Operation Multiset Similarity: ρ = 0.270
- Semantic Similarity vs Structure Alignment: ρ = 0.243

**INTERPRETATION**:
- 语义相似度与推理对齐 **弱相关** (ρ ≈ 0.24)
- 两者捕捉 **不同维度** 的相关性
- 为 H5 假设（"推理对齐比语义相似度更接近效用"）提供可测试基础

**文件**: `reasoning_alignment.json`

---

## 5. Downstream Experiment

### 5.1 实验设计

**固定变量**:
- Model: DeepSeek V4 Flash
- Temperature: 0.7
- Max tokens: 2048
- Target queries: 30 fixed
- Source IDs: shared across all arms (from retrieval cache)
- Top-k: 3 sources per target

**唯一自变量**: Memory representation
- **None**: No memory, direct reasoning
- **Case**: Concrete Case(E) memories
- **Strategy**: Abstract Strategy(E) memories
- **Paired**: Both Case(E) + Strategy(E)

**评估指标**:
- Exact Match (EM) per query
- Transition patterns (9 types)
- Correlation with diagnostics

### 5.2 Pilot Results (5 queries)

**FACT**:
- [待填充：EM rates per arm]
- [待填充：Transition counts]
- [待填充：Example transitions]

---

## 6. H1-H5 信号分析

### H1: Concrete Case 依赖语义相似度

**假设**: Case 表征的效用更依赖 semantic similarity

**观测信号**:
- [待填充：Case EM vs semantic similarity correlation]
- [待填充：Strategy EM vs semantic similarity correlation]

**结论**: [SUPPORTS / CONTRADICTS / WEAK]

---

### H2: Strategy 在低语义/高推理对齐时有效

**假设**: Strategy(E) 在语义相似度低但推理对齐高的情况下更有效

**观测信号**:
- [待填充：Strategy correct / Case wrong 的 queries]
- [待填充：这些 queries 的 semantic vs reasoning alignment]

**结论**: [SUPPORTS / CONTRADICTS / WEAK]

---

### H3: Strategy 改变负面干扰

**假设**: Strategy(E) 改变负面干扰模式

**观测信号**:
- [待填充：Case wrong 的 queries 的语义相似度分布]
- [待填充：是否 Case failures 有更低的 semantic similarity]

**结论**: [SUPPORTS / CONTRADICTS / WEAK]

---

### H4: Paired 互补性

**假设**: Paired Case+Strategy 互补而非冲突

**观测信号**:
- [待填充：Paired beats both single arms 的频率]
- [待填充：Paired worse than best single 的频率]

**结论**: [SUPPORTS / CONTRADICTS / WEAK]

---

### H5: 推理对齐更接近效用

**假设**: Reasoning alignment 比 semantic similarity 更预测 utility

**观测信号**:
- [待填充：EM vs semantic similarity correlation]
- [待填充：EM vs reasoning alignment correlation]
- [待填充：各 arm 的对比]

**结论**: [SUPPORTS / CONTRADICTS / WEAK]

---

## 7. 是否扩展到 30-Query 完整实验

**决策标准**:
1. Pilot 是否显示 **任何** H1-H5 信号？
2. 脚本是否稳定运行？
3. 数据质量是否可靠？
4. 是否存在未控制的混淆因素？

**决策**: [YES / NO]

**理由**: [待填充]

---

## 8. Next Action

**如果扩展**:
- 运行完整 30-query 实验
- 完整的 H1-H5 分析
- 撰写 Stage 36 最终报告

**如果不扩展**:
- 记录 pilot 结果作为 feasibility evidence
- 识别方法问题
- 提出改进方向或 pivot

---

## 9. 关键文件清单

- `paired_sources.json`: 90 source experiences
- `cases_clean.json`: 78 QC-passed Case memories
- `strategies_clean.json`: 78 QC-passed Strategy memories
- `qc_results.json`: QC diagnostics
- `retrieval_cache.json`: 30 targets → shared source IDs
- `target_queries.json`: 30 dev queries
- `source_embeddings.npy`: Source question embeddings
- `reasoning_alignment.json`: Oracle diagnostics
- `pilot_results.json`: 5-query pilot results (if completed)
- `experiment_results.json`: 30-query results (if completed)

---

## 10. 研究边界声明

**本研究 IS**:
- Minimal paired feasibility study
- Isolation of abstraction operator effect
- Exploratory signal detection for H1-H5

**本研究 IS NOT**:
- Large-scale performance evaluation
- Statistical proof of hypotheses
- Novelty claim without literature verification
- Production-ready memory system

**报告原则**:
- 区分 FACT / SUPPORTED INTERPRETATION / HYPOTHESIS
- 不设置任意阈值
- 报告观测模式，不强行结论
- 保留负面结果
