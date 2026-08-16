# Stage 2 报告：Baseline Alignment（针对 arXiv 2604.17979v1）

日期 2026-08-16。目标：把我们的 Case/Strategy Experience Memory 研究嵌入论文实验框架，建立 apples-to-apples baseline，回答"在 current-document grounding 之上，past experience 是否仍有增益"。
代码在 `pilot/stage2/`，产物在 `pilot/stage2/output/`。

---

## A. Baseline 官方实现审计

### A.1 是否有官方代码
**没有可用的公开官方代码仓库。** 排查过程：
- PDF 全文（提取文本）无 URL；arXiv abs 页"Code, Data and Media"区为空；ar5iv HTML 无链接。
- GitHub API 多组关键词（论文题名、作者、finqa+mem0/ollama 等）均无匹配。
- 网页搜索确认无 GitHub 链接。
论文 III-G 声称 "All code, configurations, and sample result logs are released"，但未提供可访问 URL。**因此本阶段基于论文 III 节描述自行忠实实现，所有假设显式标注。**

### A.2 论文明确描述的实现（可直接照做）
| 组件 | 论文描述 |
|---|---|
| base model | Llama 3.1 8B instruction-tuned，Ollama，temp 0.0 |
| embedding | nomic-embed-text（Ollama），Python 余弦，无向量库 |
| RAG | 文档分解为 PRE:(句子)/TABLE:(行属性值对)/POST:(行)，k=12，**无** composite filter |
| Structured Mem0 | 仅 table 派生事实，schema `entity \| column = value`（例 `total volume\|2021=637`），直接 embedding 存储（**infer=False** 绕过 LLM 抽取），ChromaDB + Mem0 库，k=12，检索后 composite-row filter |
| Mem0-Augmented | 持久化共享记忆池（完整文档 + 每轮 Q/A 追加），free-form 存储检索 |
| Baseline | 完整文档上下文 D 注入 |
| 符号归一化 | 后处理：取最后数值 token、会计负数、fraction↔percent（题面含 percent 语境）、gold 精度自适应容差 |
| 指标 | Exact / Close / Corrected 变体 / Parse / Judge |

### A.3 必须自行补齐的部分（论文未给全，全部标注）
1. **prompt 模板**：论文只说"同一模板，仅 context 不同"。自定一套并统一。
2. **事实序列化细节**：`entity | column = value` 的列头/行首映射（[假设 A]）。
3. **composite-row filter 精确规则**：论文未给代码。自定 [假设 C]：单元格规范化为单一数值（会计负数 -36 ( 36 ) → -36）则保留；复合/范围/无数值则丢弃。实测丢弃率仅 8%，非过度激进。
4. **492 样本子集**：论文未说明如何选取。用固定种子随机 492 并记录（seed 20260816）。
5. **Corrected 容差具体值**：自定 [假设 D]：close = |c−g| ≤ max(1%·|g|, abs_tol)，abs_tol=0.5(大数)/0.01(小数)；percent 语境下候选集 {c, c×100, c÷100}。
6. **mem0aug 记忆检索**：论文说"共享池 + top-k 检索"，未给 k。用 40 条最近记忆拼接（文档化）。

### A.4 Structured Mem0 到底是什么（关键结论）
**Structured Mem0 = current-document factual grounding，不是 cross-example experience memory。**
- 它只处理**当前文档**：table 行 → `entity | column = value` 原子事实，存库、检索 top-k、注入 prompt。
- 它**不利用任何跨样本的历史 solved examples**（FinQA 单轮，无跨样本记忆；ConvFinQA 时按 dialog 隔离）。
- 与我们 Case/Strategy Experience Memory 的本质区别：
  - Structured Mem0：`当前文档的实体/数值事实 grounding`（解决 operand/entity/year 定位）。
  - Case Memory：`其他 train 样本的具体 solved experiences`（跨样本类比迁移）。
  - Strategy Memory：`从 train 抽象的可复用推理方法`（跨样本方法迁移）。
- 结论：**Structured Mem0 是我们的"当前文档 grounding 层"，Case/Strategy 是它之上的"跨样本经验增强层"，两者职责不重叠。** 我们不改 Structured Mem0 的核心职责（详见 C 模块边界）。

---

## B. Reproduction

### B.1 Reproduction 结果（free-form 输出 + Corrected 指标，n=492）

| 方法 | 论文 Corr.Exact | 我们 Corr.Exact | 论文 Corr.Close | 我们 Corr.Close |
|---|---|---|---|---|
| Baseline | 0.319 | 0.378 | 0.378 | 0.632 |
| RAG | 0.256 | 0.329 | 0.311 | 0.549 |
| Structured Mem0 | **0.354** | 0.242 | **0.423** | 0.402 |
| Mem0-Augmented | 0.236 | **0.541** | 0.293 | 0.644 |

**排名与论文相反**（论文：Structured > Baseline > RAG > Mem0-Aug；我们：Mem0-Aug > Baseline > RAG > Structured）。按要求排查了原因：

### B.2 排名反置的根因（三方面）
1. **模型能力差异（主因）**。论文用 Llama 3.1 8B（弱指令跟随、58% 多数值输出、格式违规多），其 baseline 被格式噪声拖累（Judge 0.583 vs Corr.Exact 0.319 差 27pp）。Structured 的紧凑事实恰好规避了 Llama 的格式问题。DeepSeek-V4-flash 能干净处理 full-doc 上下文（baseline Corr.Exact 0.378 甚至略超论文的 Structured），Structured 的"紧凑性优势"消失。**这印证了论文自己 limitation 里承认的"inversion 未必 model-agnostic"。**
2. **Structured 的 table-only 覆盖损失**。论文明确 Structured 只存 table 派生事实。诊断：492 样本中 **39% 需要文本事实，22% 纯文本问题（无表格事实）**——这些题目 structured 结构性无法答对（模型抓到错误的表行数值，如 ILMN gold `divide(50,5154639)` 但输出 `divide(38957,187103)`）。RAG 含文本所以影响小。
3. **mem0aug 的共享池设计 = 隐式跨样本答案记忆**。论文把 Mem0-Augmented 定义为"共享记忆池 + Q/A 追加"。在 FinQA 单轮上，这等价于把之前样本的 Q/A 存进记忆、按相似度检索。强模型能直接利用先前相似题的答案（≈ 一个 free-form 版的 Case Memory），故分数虚高。**这不是论文期望的"mem0 最弱"行为，而是共享池在强模型下的泄漏式副作用。**

### B.3 论文三个机制点的核对
- **Structured 是否优于 RAG / vanilla memory？** 否（我们模型下）。structured 0.366(unified)/0.242(repro) < baseline。
- **RAG 是否存在 operand distractor？** 部分存在：unified 里 rag exec(0.545) < baseline(0.571)，且抽查见 RAG 对 percent-change 输出 "462%"（明显错值）。但严重度远低于论文（论文 RAG 远低于 baseline）。
- **Structured facts 是否减少 grounding ambiguity？** 我们模型下否：structured program_match(0.463) < baseline(0.516)。原因是丢失操作数而非减少歧义。

### B.4 Reproduction 结论
论文的"Structured 在 FinQA 上最优"趋势在 DeepSeek-V4-flash 下**不成立**。这是模型相关的架构现象（论文自己也承认该风险），加上 mem0aug 共享池泄漏放大。**本阶段不把"复现论文数字"作为目标，而是把"架构比较的公平性"作为目标。**我们的增量发现（D/E 节）不依赖论文的具体排名。

---

## C. Unified Experimental Setup（apples-to-apples）

| 控制项 | 设定 |
|---|---|
| split / sample | dev，固定种子随机 **492**（seed 20260816），匹配论文 n=492 |
| base model | DeepSeek-V4-flash[1m]（Anthropic 兼容端点），temp 0.0，thinking disabled |
| embedding | bge-small-en-v1.5（替代 nomic-embed-text，CPU） |
| prompt | 每输出模式一个模板，全臂共享；仅 context 段不同 |
| 输出格式 | reproduction: free-form 数值；unified: FinQA 嵌套 program |
| retrieval budget | 事实 k=12（论文默认）；Case top-4；Strategy top-3 |
| context budget | full-doc: pre 40 + post 40 句 + 全表；structured: top-12 原子事实；经验: 4 case + 3 strategy |
| evaluation | reproduction: Corrected Exact/Close；unified: 官方 FinQA execution/program accuracy（pilot/executor，gold 2000/2000 自检） |
| random seed | 全流程固定 |

主指标为 **FinQA execution/program accuracy**（更接近官方 reasoning evaluation）；reproduction 指标（Corrected）作为与论文对比的辅助指标。**未改动 evaluator 让数字变好看。**

### C.1 模块边界（论文 grounding + 我们的经验层）
```
Current Query + Current Financial Document
        ↓
  Structured Fact Grounding   ← 继承论文（table 原子事实，k=12，composite filter）
        ↓
  Past Experience Augmentation ← 我们的扩展
   /        |        \
 Case    Strategy    Both       (or None)
   \        |        /
        ↓
      LLM
```
- **Case Memory**：train 具体 solved experiences（`pilot/output/case_memory.json`，6251 条）。
- **Strategy Memory**：train 抽象推理策略（`strategies_clean.json`，28 条规范策略）。
- **边界判断**：Structured 只处理当前文档事实（operand/entity/year grounding）；Case/Strategy 只处理跨样本经验（类比/方法迁移）。职责不重叠，实现上无冲突。
- **潜在冲突点**：prompt 长度（structured facts + 4 case + 3 strategy 可能较长）；以及若 base model 无法区分"当前文档事实"与"历史案例数值"，可能把案例数字抄进答案——prompt 已显式提醒"do NOT copy their numbers"。

---

## D. Incremental Results（n=492，unified FinQA exec / program）

| Arm | exec | program | vs grounding |
|---|---|---|---|
| baseline (full-doc) | 0.571 | 0.516 | — |
| rag | 0.545 | 0.555 | −2.6pp exec |
| structured | 0.366 | 0.463 | — |
| **struct_case** | 0.482 | 0.628 | **+11.6 / +16.5** |
| struct_strategy | 0.407 | 0.492 | +4.1 / +2.9 |
| struct_both | 0.478 | 0.618 | +11.2 / +15.5 |
| **fulldoc_case** | **0.699** | 0.683 | **+12.8 / +16.7** |
| fulldoc_strategy | 0.604 | 0.565 | +3.3 / +4.9 |
| fulldoc_both | 0.669 | 0.677 | +9.8 / +16.1 |

**关键回答（用户 §6 的核心问题）：在已有 current-document grounding 后，past experience 仍有显著增益。**
- full-doc grounding 上：case +12.8pp、strategy +3.3pp。
- structured grounding 上：case +11.6pp、strategy +4.1pp。
- **增益不依赖 grounding 类型**：无论 grounding 好坏，经验都大幅提升。且 grounding 质量越高收益越大（fulldoc_case 0.699 > struct_case 0.482）。

### D.1 分 bucket（exec，关键臂）
| bucket | n | baseline | structured | struct_case | fulldoc_case |
|---|---|---|---|---|---|
| A comparison | 5 | 1.000 | 0.200 | 0.600 | 0.800 |
| B table_agg | 16 | 0.250 | 0.250 | 0.812 | 0.938 |
| C unitscaling | 25 | **0.000** | 0.040 | 0.280 | **0.400** |
| D multistep | 5 | 0.200 | 0.200 | 0.200 | 0.200 |
| E 3step | 7 | 0.143 | 0.000 | 0.000 | 0.143 |
| F 2step | 165 | 0.624 | 0.424 | 0.485 | 0.733 |
| G 1step | 269 | 0.621 | 0.383 | 0.494 | 0.714 |

Case 价值集中在：**单位换算（C，baseline 0→0.400）、表格聚合（B，0.250→0.938）、单双步（G/F，+11~17pp）**——与我们 Clean Oracle 的"Case=模板/行标签/单位惯例迁移"结论一致，且在新 grounding 框架下稳健。

---

## E. Experience Complementarity After Structured Grounding

### E.1 各 grounding 族内的互补性（exec）
| grounding 族 | case_only | strategy_only | both 对 | both 错 | best_fixed | oracle(族内) | gap |
|---|---|---|---|---|---|---|---|
| full-doc (baseline 族) | 69 | 22 | 275 | 126 | 0.699 | 0.783 | **+8.3pp** |
| structured 族 | 53 | 16 | 184 | 239 | 0.482 | 0.537 | **+5.5pp** |

### E.2 naive Both 干扰
- full-doc 族：both_wrong_but_single = 43；both_all(0.669) < fulldoc_case(0.699)。
- structured 族：both_wrong_but_single = 25；struct_both(0.478) < struct_case(0.482)。
**naïve Both 拼接仍在两种 grounding 下都产生负干扰。**

### E.3 Oracle（9 个 unified 臂）
- Best Fixed = **fulldoc_case 0.699**
- **Oracle = 0.829，Oracle Gap = +13.0pp**

---

## F. Research Implication

### 用户 §7 的检验
"如果加入 Structured Mem0 后 Case 增益几乎消失 → framing 需调整；如果仍存在 Case-only/Strategy-only/naive Both interference/non-trivial Oracle Gap → 研究问题变强。"

**结果：Structured grounding 之后，Case 仍 +11.6pp、Strategy +4.1pp；case-only 53、strategy-only 16、naive both 干扰 25、族内 oracle gap +5.5pp——全部仍然存在。→ 研究问题被强化，而非否定。**

### 但必须记录的三点重要修正（诚实结论）
1. **Structured 继承层的有效性存疑**：在我们（DeepSeek）模型下，论文的 table-only Structured Mem0 弱于 full-doc baseline（0.366 vs 0.571）。论文的"Structured 最优"是 Llama-8B 弱模型的格式噪声红利，非通用架构规律。**因此"继承 Structured 作为 grounding 层"并不明显优于直接给全文。**
2. **经验增益是 grounding 无关的**：经验在 full-doc（+12.8pp）和 structured（+11.6pp）两种 grounding 上都大幅提升。研究主张应从"Structured 之上加经验"弱化为"current-document grounding 之上加跨样本经验（grounding 无关）"——这反而让主张更稳健。
3. **grounding 质量放大经验价值**：fulldoc_case(0.699) 远高于 struct_case(0.482)。好的 grounding + 经验 >> 弱 grounding + 经验。selector/router 的增益空间主要来自"把 grounding 与经验都选对"。

### 判定：**CONDITIONAL GO**
- **GO 的部分**：核心研究问题（past experience 在 current-document grounding 之上仍有大增益；Case/Strategy 互补、naive Both 干扰、Oracle gap 在 grounding 之后依然存在）**成立且被强化**。这支撑继续做 adaptive experience selection。
- **CONDITION 的部分**：(a) 论文的 Structured 继承层在我们模型下不占优——下一阶段应把 grounding 层视为可配置（full-doc 或 structured），而不是预设 Structured 最优；(b) reproduction 指标与论文排名不同——报告必须同时给两套指标，不宣称"复现论文"；(c) mem0aug 共享池的泄漏式高分为论文设计产物，不代表真实方法能力。

---

## G. 下一阶段建议

1. **Grounding 层配置化**：不预设 Structured 最优。将 grounding（full-doc / structured facts）作为实验因子之一，与 experience 因子正交（本报告的 2×3 已提供基准）。
2. **Adaptive Memory/Router 的对象明确为"experience 层"**：Oracle gap（9 臂 +13pp）主要来自 case-only(69+53) 与 ground/experience 组合选择。router 候选空间 = {none, case, strategy, both} × grounding，且须包含 None（A/B 桶经验甚至无益时）。
3. **经验增益上限**：fulldoc_case 0.699 已超过论文任何架构；strategy 单独增益小（+3~4pp）但存在独占正确（22+16 例）——selector 需能识别 strategy 何时胜出（长链/比较/平均类）。
4. **修复 reproduction 的下一步**（可选）：若需与论文对齐，应跑一个真实 8B 本地模型（Ollama + Llama 3.1 8B）做纯 reproduction；但受限于本机 GPU/torch 不兼容，暂不可行。
5. **不实现 router**：本阶段到此为止。若继续，进入 adaptive experience selector 设计。

---

## 工程记录
- 代码：`pilot/stage2/{s2config,s2_facts,s2_retrieval,s2_prompts,s2_eval,s2_evaluate,diagnose,run}.py`
- 产物：`stage2/output/arm_outputs.json`（13 臂 × 492 原始输出）、`evaluation.json`、`cache.jsonl`（可恢复）
- 复用：`pilot/executor.py`（官方语义，gold 2000/2000 自检）、`pilot/output/case_memory.json`、`strategies_clean.json`
- 决策日志：`pilot/DECISIONS.md`（新增 Stage 2 章节）
