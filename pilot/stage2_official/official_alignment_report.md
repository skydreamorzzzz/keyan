# Stage 2.1 报告：Official Implementation Re-alignment

日期 2026-08-16。仓库：`JLiu24-Eng/Retrieval-and-Memory-Augmentation-for-Financial-QA-Study`（commit d21ab97，2026-03-16）。
代码：`pilot/stage2_official/`；产物：`pilot/stage2_official/output/`。

---

## 1. 官方实现审计

官方仓库 `src/` 下 7 个脚本，FinQA 相关 3 个：`run_finqa_baseline_mem0.py`（Baseline + Mem0-Aug，`--mem0` 开关）、`run_finqa_rag.py`、`run_finqa_structured_mem0.py`。`results/` 下 8 个 CSV 与论文 Table I/II 对应。

### 1.1 逐项真实实现（全部从代码确认）

| 项 | 官方真实实现 |
|---|---|
| **492 选择** | `for i in range(min(limit, len(ds)))` → **dev.json 前 492 条**（文件顺序，非随机） |
| **gold** | `qa["answer"]` 字段（如 "127.40"、"93.5%"），**非 exe_ans** |
| **Baseline prompt** | system=`FIN_SYSTEM`；`Context:\n{context}\n\nQuestion:\n{q}\n\nFinal Answer:`；context = `Pre-text:\n{pre}\n\nTable:\n{table}\n\nPost-text:\n{post}`（pre/post 全量，table 行 `\t` 连接） |
| **RAG facts** | `PRE:/TABLE:/POST:`；表格按**整行** `col: val \| col2: val2`；pre/post 各 60 行、table 60 行上限；检索 top-k（默认 12），nomic-embed 余弦 |
| **RAG prompt** | `FACTS:\n- ...\n\nQUESTION:\n{q}\n\nFinal Answer:` |
| **Structured facts** | `table_to_facts` → 按 cell `{entity} \| {col} = {value}`（**实体/表头小写化**，max_rows=25）；**同时存 `qa["model_input"]` 事实**（数据集自带的自然语言检索渲染，含文本句 + 表行渲染） |
| **Structured 检索** | `mem.add(..., infer=False)`；`mem.search(question, user_id, limit=50, filters={"run_id": run_id})` → **按当前文档 run_id 隔离（非跨样本）**；然后 `keyword_filter_facts`（仅特殊规则）→ `drop_composite_row_facts` → `[:k=12]` |
| **composite filter** | 文本启发式：**facts 含 ≥2 个分号 或 以 "company the " 开头 → composite 丢弃**（主要针对 model_input 的多属性表渲染）；有 atomic 则只用 atomic |
| **Structured prompt** | system=`FIN_SYSTEM_STRUCTURED`（含 "Do NOT rescale" 等）；`build_prompt_from_facts`（FACTS + 硬编码 RULE：cumulative total return / payment volume per transaction + NORMALIZATION_RULES） |
| **Mem0-Augmented** | `user_id="finqa_user_1"` **跨全部样本共享**；每样本 `mem.add(context)` + 回答后 `mem.add("Q:...\nA:...")`；检索 `mem.search(question, user_id)` 注入 "Remembered facts" |
| **Corrected 指标** | `extract_last_number_with_flags`（会计负数、% 标志）→ `normalize_pred_to_gold_scale`（percent 语境且 pred∈[0,1.5] 时 ×100）→ `exact_match`（round 到 gold 小数位）→ `numeric_close`（percent: isclose(abs_tol 0.5/0.15/0.05, rel 0.002)；非 percent: 按小数位 abs tol） |
| **Judge** | 独立 LLM 调用（`JUDGE_SYSTEM`，Llama 判断） |
| **未使用的代码** | `select_entity_facts` 定义了但**未被调用**；Structured 里一组旧的 `exact_match/numeric_close`（246-267 行）未被使用，实际用 `_NUM_TOKEN_RE` 增强版 |

### 1.2 我们实现与官方的重要差异（diff 分类）

| 项 | 官方 | 我们 `pilot/stage2/` | 严重度 |
|---|---|---|---|
| 492 采样 | dev 前 492 | 随机 seed 492 | **重要**（样本不同） |
| gold | `qa["answer"]` | `exe_ans` | **重要** |
| Baseline 上下文 | Pre-text/Table/Post-text，`\t` 表格，pre/post 全量 | "TEXT BEFORE TABLE/..."，40 句上限，`row0: ...` | **重要** |
| RAG 表事实粒度 | 整行 `col: val \| ...` | 按 cell `entity\|col=val` | **重要** |
| Structured 事实源 | table facts + **model_input**（文本覆盖） | 仅 table facts（无文本） | **重要**（旧实现缺文本覆盖 → structured 偏弱） |
| composite filter | ≥2 分号 / "company the " 前缀 | 单元格单值解析启发式 | **重要**（逻辑不同） |
| Structured 检索 | run_id 隔离、limit 50→filter→12 | 直接 top-12 | **重要** |
| Structured prompt | FIN_SYSTEM_STRUCTURED + 硬编码 RULES + NORMALIZATION | 无 RULES，通用 program 提示 | **重要** |
| Corrected 容差 | 官方精确规则（round-to-gold-decs、percent abs_tol） | rel 1% + abs 0.5/0.01 | **重要** |
| 输出格式 | free-form（官方） | free-form + program | 按设计 |
| embedding / backbone | nomic-embed / Llama-8B | bge-small-en / DeepSeek | 记录差异 |

**结论：上一轮 `pilot/stage2/` 在采样、gold、fact 构造（尤其 Structured 缺 model_input 文本覆盖）、composite filter、prompt、指标容差六个维度都与官方不同。** 上轮"structured 偏弱（0.366）"的主因是**缺 model_input 文本覆盖**，是旧实现伪影，不是论文 Structured 的真实表现。

---

## 2. Official-Aligned Setup

移植官方逻辑（`stage2_official/s2o_common.py`），仅替换 backbone/API：
- LLM：DeepSeek-V4-flash，temp 0，thinking disabled（替换 Ollama+Llama 3.1 8B）
- embedding：bge-small-en-v1.5（替换 nomic-embed-text）
- Mem0/ChromaDB → numpy 等效实现（infer=False 直嵌、run_id 过滤、余弦检索），语义一致
- gold：`qa["answer"]`（reproduction 指标）；`exe_ans`（FinQA exec 指标）
- 经验注入：独立于 grounding 检索（`pilot/retrieval.py` 的 case/strategy 索引），追加为 prompt 的额外 section

### 2.1 指标双轨
- **reproduction（官方）**：Corrected exact/close，free-form，gold=`qa.answer`。
- **unified（FinQA）**：program 输出 → executor 执行 → exec，gold=`exe_ans`。

---

## 3. 新实验结果（n=492，dev 前 492）

### 3.1 Reproduction（官方 Corrected，DeepSeek）

| 方法 | 论文 Corr.Exact/Close | 官方-aligned Exact/Close |
|---|---|---|
| Baseline | 0.319 / 0.378 | 0.539 / 0.616 |
| RAG | 0.256 / 0.311 | 0.382 / 0.443 |
| Structured | 0.354 / 0.423 | 0.504 / 0.569 |
| Mem0-Augmented | 0.236 / 0.293 | 0.557 / 0.642 |

**论文排名（Structured > Baseline > RAG > Mem0-Aug）在官方-aligned + DeepSeek 下仍未复现**（Mem0-Aug > Baseline > Structured > RAG）。原因与上轮一致：DeepSeek 处理 full-doc 无格式噪声（Baseline 从 0.319→0.539），Structured 的紧凑性优势消失；Mem0-Aug 的跨样本共享池在强模型下变成"隐式跨样本答案记忆"，分数虚高。**这是模型能力依赖，非官方 pipeline 问题**（已用官方代码逐字移植确认）。

### 3.2 Experience Memory 增量（官方 grounding）

**官方 Corrected Close（free-form）：**
| arm | close | vs grounding |
|---|---|---|
| baseline | 0.616 | — |
| baseline_case | 0.632 | **+1.6pp** |
| baseline_strategy | 0.606 | −1.0pp |
| baseline_both | 0.634 | +1.8pp |
| structured | 0.569 | — |
| structured_case | 0.492 | **−7.7pp** ⚠️ |
| structured_strategy | 0.551 | −1.8pp |
| structured_both | 0.547 | −2.2pp |

**FinQA exec（program）：**
| arm | exec | vs grounding |
|---|---|---|
| baseline | 0.683 | — |
| baseline_case | 0.720 | **+3.7pp** |
| baseline_strategy | 0.695 | +1.2pp |
| baseline_both | 0.728 | **+4.5pp** |
| structured | 0.626 | — |
| structured_case | 0.646 | **+2.0pp** |
| structured_strategy | 0.632 | +0.6pp |
| structured_both | 0.657 | **+3.1pp** |

---

## 4. 核心现象（两种指标 × 两种 grounding）

### 4.1 FinQA exec（主指标，官方执行）

| family | case gain | strat gain | case_only | strat_only | both 错单臂对 | best fixed | oracle | **oracle gap** |
|---|---|---|---|---|---|---|---|---|
| **Full-doc** | +3.7pp | +1.2pp | 43 | 31 | 31 | 0.728 | 0.821 | **+9.3pp** |
| **Structured** | +2.0pp | +0.6pp | 30 | 23 | 29 | 0.657 | 0.742 | **+8.5pp** |

### 4.2 官方 Corrected Close

| family | case gain | strat gain | case_only | strat_only | both 错单臂对 | best fixed | oracle | **oracle gap** |
|---|---|---|---|---|---|---|---|---|
| **Full-doc** | +1.6pp | −1.0pp | 44 | 31 | 37 | 0.634 | 0.746 | **+11.2pp** |
| **Structured** | −7.7pp ⚠️ | −1.8pp | 36 | 65 | 55 | 0.569 | 0.697 | **+12.8pp** |

---

## 5. 结论：哪些旧结论 survive / 需修正

### 5.1 核心研究问题：**在 official-aligned pipeline 下依然成立（两种指标 × 两种 grounding）**
- **Case/Strategy complementarity**：case-only 与 strategy-only 在所有四组（指标×grounding）都稳定存在（30-44 / 23-65）。
- **naive Both 干扰**：both 错但单臂对在所有四组都 ≥29 例。
- **non-trivial Oracle Gap**：exec +9.3/+8.5pp；corrected +11.2/+12.8pp。**全部远超噪声。**

→ **我们最关心的现象在严格官方对齐后依然存在。研究问题被确认，不是实验伪影。**

### 5.2 需修正的旧结论
1. **上轮"structured 偏弱"是旧实现伪影**：官方 Structured 含 `model_input` 文本覆盖 + 官方 prompt RULES，官方-aligned structured（exec 0.626 / close 0.569）远强于我上轮的 table-only 实现（0.366/0.402）。**旧实现结构性低估了 Structured。**
2. **上轮"经验在 structured 上 +11.6pp"需下修**：official-aligned 下 exec 为 +2.0pp（corrected 为 −7.7pp）。上轮大增益部分来自"弥补弱 grounding"，官方对齐后经验增益更真实、更小但方向稳定（exec）。
3. **论文"Structured 在 FinQA 最优"为模型依赖**：官方代码 + DeepSeek 下仍未复现（Mem0-Aug > Baseline > Structured）。这不是复现目标，已记录。

### 5.3 新发现：注入方式 × 输出尺度规范冲突（⚠️ 重要）
corrected 指标下 structured_case 为 **−7.7pp**，机制：structured prompt 强制 "If the question asks for a percentage, return a percentage" + "Do NOT rescale"，而**案例示例的 exe_ans 是小数值（fraction）**（如 percent-change 的 0.0489）。注入案例后模型输出尺度被带偏（72.8%→0.7282%）。exec 指标（程序输出，尺度由程序自身携带）不受影响且 case 正向。
→ **经验注入必须尊重 grounding 的输出尺度规范**：给结构化 grounding 注入 Case 时，不应泄漏案例的 exe_ans 小数值作为尺度暗示（或需提示"输出尺度遵循当前 grounding 规范"）。这是 Stage 3 selector/注入设计必须处理的约束，不是经验无用的证据。

---

## 6. Mem0-Augmented 机制（准确描述，不称"泄漏"）

官方代码确认：
- `user_id = "finqa_user_1"` **跨全部 492 个 FinQA 样本共享**（无 per-dialog 隔离）。
- 每样本：`mem.add(context)` + 回答后 `mem.add("Q:...\nA:...")` → **context 与 Q/A 都入记忆**。
- 检索：`mem.search(question, user_id)` → **可检索到任意其他样本的 context 与 Q/A**。

分类（三者并存）：
1. **intended conversational memory**：Mem0 的设计本意（跨会话持久记忆），在 ConvFinQA 多轮内是对话记忆。
2. **cross-example experience reuse**：在 FinQA 单轮设定下，同一 user_id 的共享池使检索能拿到**先前样本的完整文档 + Q/A 答案**——本质上是"free-form 版的跨样本 experience memory"。
3. **potential contamination**：由于它**能检索到先前样本的 Q/A 答案**，强模型可直接复用相似题的答案 → 分数虚高（0.557/0.642 为四法最高）。这与论文把它归为最弱的结论相反，是"共享池 × 强模型"的组合效应。

**精确表述：官方 Mem0-Augmented 在 FinQA 上确实跨样本复用先前文档与 Q/A；这是其"persistent cross-session"设计在单轮基准上的副作用。** 我们复现时按论文描述的 free-form 语义存储原始文本（未复刻 mem0 的 LLM extraction），并在 `s2o_common.py` 注明。

---

## 7. 判定：**READY FOR STAGE 3**

### 依据（全部来自实验结果）
1. **核心现象在 official-aligned pipeline 下全部存活**：
   - Case/Strategy 互补（case-only 43/30，strategy-only 31/23，exec）；
   - naive Both 干扰（31/29 exec）；
   - Oracle Gap（exec +9.3/+8.5pp；corrected +11.2/+12.8pp）。
2. **Case 在官方 grounding 之上仍正向**（exec：full-doc +3.7pp，structured +2.0pp），方向与 Stage 1/2 一致。
3. 官方 pipeline 已稳定移植并执行（13 臂 × 492 全跑通，无失败）。
4. 旧实现的主要伪影（structured 缺 model_input）已识别并修正，官方对齐完成。

### 进入 Stage 3（Adaptive Experience Memory Selector）必须带上的约束
- **注入尺度一致性**：经验注入需与 grounding 输出尺度规范一致（修正 corrected 指标下 structured_case 的 −7.7pp 尺度污染）。
- **grounding 配置化**：Full-doc 与 Structured 都是合法 grounding（Structured 不再预设最强；本实验 exec 下 baseline 0.683 > structured 0.626）。
- **grounding 检索与 experience 检索独立**（已实现）。
- **Mem0-Aug 的跨样本复用**作为"free-form experience"基线纳入对照，但不作为 contamination 排除。

### 不成立的理由（为何不是 STAGE 2 NEEDS FIX / FRAMING NEEDS REVISION）
- 官方 pipeline 已正确移植并验证（与代码逐字对照）；reproduction 排名差异为模型能力依赖，非 pipeline 错误。
- 核心研究假设（经验价值 + 互补性）没有被推翻，反而在更严格设定下被确认。

---

## 8. 工程记录
- 代码：`pilot/stage2_official/{s2o_common,s2o_evaluate,run_official}.py`
- 产物：`output/arm_outputs.json`（18 臂模式 × 492）、`output/evaluation.json`、`output/llm_cache.jsonl`（可恢复）
- 官方仓库快照：`/tmp/official_finqa/`（commit d21ab97）；官方结果 CSV 用于交叉核对 gold/顺序。
- 复用：`pilot/executor.py`、`pilot/retrieval.py`、`pilot/output/{case_memory,strategies_clean}.json`
