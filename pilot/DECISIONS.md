# Oracle Pilot 决策日志（Stage 2）

所有关键实验设计决定与理由。时间戳 2026-08-16。

## 1. 采样
- **dev 分层 150 条，配额式**（实际 143：A/D 桶 dev 池不足）。
- 配额：A_comparison_yesno 12, B_table_aggregation 14, C_unitscaling_multi 18, D_multistep4plus 12, E_3step 12, F_2step 44, G_1step 38。
- **理由**：自然分布单步占 55%，长链/表格聚合/比较类型样本太少，无法分析分类型互补。结构化类型正是 Case/Strategy 差异最可能出现的地方。
- **后果/风险**：整体 accuracy 不代表自然分布；报告同时给 bucket 分层 + 自然分布视角。不碰 test。

## 2. Case Memory
- **全量 train 6251 条直接入库，无 LLM 重写**。
- 字段：case_id/report/company/question/problem_kind(bucket)/n_steps/struct/gold_facts/program/program_re/steps/exe_ans/answer/explanation/retrieval_text。
- **理由**：第一版保持"真实案例"，避免重写引入偏置；字段全部来自原数据 + 最小派生（bucket）。
- 检索文本 = question + bucket + gold_facts（渲染事实）。

## 3. Strategy Memory
- **从 top-25 struct 聚类 + LLM 抽象生成 44 条策略**（覆盖 ~96% train 程序结构）。
- 每个策略含：name/problem_type/problem_pattern/operand_roles/procedure/formula/template(槽位化 V1,V2)/units_convention/caveats/example_ids。
- **约束**：禁止公司名、年份、具体数值、表行标签进入策略本体。
- QC：人工审查 44 条，修复 S041 模板（含 `...`）、补充复利策略 S044（exp 未进入 top-25 struct）、标记 S020 低置信。
- **已知局限**：同一 struct 可对应多语义（如 %change 三种变体）；部分模板是近似（const_3 等按 case 变化）。

## 4. Retrieval
- **模型**：BAAI/bge-small-en-v1.5（英文检索 baseline），CPU（GPU 驱动与 torch 2.13 不兼容）。
- **top-k**：Case 4，Strategy 3。
- **决策**：不排除同公司检索（公司重叠是待测量的 confound，不是要消除的 bug）。
- **策略检索文本**：初版用抽象术语，检索效果差；改为 example questions 优先 + name/type/template 标签，命中改善但仍非完美。
- **量化结果**：case 同 struct 命中 63.6%（top-4）；strategy 精确族命中 32.9%（top-3），语义近族命中更高。**结论：strategy retrieval 是显著 confound，分析必须做 retrieval-conditioned 视图。**

## 5. 4 臂实验
- 四臂唯一差异是 memory 段；report context（pre_text 前 30 + post_text 前 30 + 全表）四臂完全相同。
- 模型：DeepSeek-V4-flash[1m]（Anthropic 兼容端点），temperature 0，thinking disabled，max_tokens 2500。
- 输出格式：嵌套 program_re 单行。解析器规范化：compare(→greater(、顶层 `>` → greater(、linear 形式自动识别。
- 并发 12，缓存按 arm|qid|prompt-hash 存盘可恢复。

## 6. 评估
- 主指标：execution accuracy（官方语义执行器，自检 2000/2000 gold 正确）；辅：official round-5 精确比较、结构模板匹配。
- Oracle = 每题四臂任一正确；Best Fixed = 四臂整体最高；Oracle Gap = Oracle − Best Fixed。
- Contingency：Case-only / Strategy-only / both / neither。
- 干扰：Both 错但 Case 或 Strategy 对（Both 臂带来负干扰）。
- 归因维度：bucket / n_steps / unit_scaling(const_) / yesno / company_in_train / retrieval-conditioned。

## 7. 明确不做（本阶段）
- 不做 selector/router 设计；不做全量 6251 策略池；不做复杂 retriever（BM25 混合等留待后续）。

## 8. Clean Oracle 阶段决策（2026-08-16 下午）

### Strategy 清洗
- 44 → 28 条规范策略。合并：%change 三种变体（S002/S019/S022）→ C02 规范 fraction；求和（S005/11/24/34）→ C04/C05；平均（S007/16/25）→ C06/C07；ratio（S001/6/28/31）→ C01。删除 S020（低置信）、S037（并入 C03）、S041（并入 C04）。
- 尺度/单位约定全部来自 train 统计：percent-change 族 fraction 95.2%（规范=小数）；const_100 全量仅 4.1%；平均除数=值个数；const 因子由表头单位决定（通用规则，非 dev）。
- 复利策略（exp）人工补充，标注来源。

### Strategy 检索（简单可解释）
- 从纯 embedding 改为 **case-anchored 候选过滤**：top-8 cases 的 struct → 候选策略（program_family 匹配）→ 按 case 共现次数 + embedding 排序。
- family-hit@3：37.8% → 64.3%（strat）/ 76.0%（nat）。
- 理由：case 检索可靠（同 struct 63.6%），用它缩小策略候选，不额外训练/复杂化。
- 注意：strategy-only 臂在内部用 case 检索辅助（不把 case 给模型），不算 memory mixing。

### Cross-Company Case
- case_cc = 检索排除同公司。同公司贡献 case_all−case_cc：strat +4.9pp / nat +2.0pp；但 case_cc 仍 >> no（+4.9/+10pp）→ Case 收益非纯同公司。

### 双样本
- 保留 strat 143；新增 nat 250（种子 20260817，纯随机，与 strat 重叠 36）。所有结论双视图报告。

### Pipeline bug 修复（重要，防复发）
1. run_arms 中 `for arm,use_case,use_strat,xcomp in ARMS:` 循环后 `xcomp` 泄漏为最后值 True → 所有 case 臂误用 exclude_company。修复：每 query 显式计算 rc_all/rc_cc。
2. prompts.build_prompt 的 case 条件元组漏了 "case_all" → case_all 臂无案例退化为 no-memory。修复：补入元组。
- 教训：跨脚本共享的臂名集合应集中定义，避免字符串枚举不一致。

### 最终判定
- GO（进入 Adaptive Memory Selector 设计）。依据见 report_clean_oracle.md §7。

## 9. Stage 2 Baseline Alignment 决策（2026-08-16 晚）

### 论文/代码审计
- 论文 arXiv 2604.17979v1 声明 release code 但无 URL；GitHub/arXiv/ar5iv 均无官方仓库 → 基于论文 III 节自行忠实实现，所有假设标注（fact 序列化、composite filter、492 子集、Corrected 容差、mem0aug 记忆检索）。

### 统一实验框架
- 492 dev（seed 20260816）双指标：reproduction（free-form + Corrected Exact/Close）+ unified（program + FinQA official exec/program）。
- 2×3 因子设计：grounding{full-doc, structured} × experience{none, case, strategy, both}。
- base model 统一 DeepSeek-V4-flash；embedding 以 bge-small-en 替代 nomic-embed-text；k=12 事实。

### 关键发现（诚实记录）
- **Reproduction 排名与论文相反**（Mem0-Aug > Baseline > RAG > Structured）。根因：模型能力（强模型处理 full-doc 无格式噪声）、Structured table-only 覆盖损失（22% 纯文本问题结构性失败）、mem0aug 共享池=隐式跨样本答案记忆（泄漏式虚高）。
- **经验增益 grounding 无关**：full-doc 上 case +12.8pp、structured 上 +11.6pp；互补性/干扰/Oracle gap 在两种 grounding 下都持续 → 研究问题被强化。
- 但 **Structured 继承层在我们模型下不占优**（0.366 < baseline 0.571），下一阶段 grounding 应配置化，不预设 Structured 最优。
- 判定：**CONDITIONAL GO**。

## 10. Stage 2.1 Official Re-alignment 决策（2026-08-16）

### 官方仓库
- `JLiu24-Eng/Retrieval-and-Memory-Augmentation-for-Financial-QA-Study`（commit d21ab97）。上一轮 stage2 无官方代码，此轮已拉到官方代码逐字对齐。
- 关键差异：492 = dev 前 492（非随机）；gold = qa.answer（非 exe_ans）；Structured 含 model_input 文本覆盖（旧实现缺此 → structured 被低估）；composite filter = ≥2 分号/"company the "前缀；prompt 有硬编码 RULES；Corrected 容差为官方精确规则。

### official-aligned 实现
- 移植官方逻辑（s2o_common.py），仅替换 backbone（DeepSeek）与 embedding（bge），Mem0/ChromaDB→numpy 等效。
- 双指标：官方 Corrected（free-form, gold=qa.answer）+ FinQA exec（program, gold=exe_ans）。

### 结果与判定
- 核心现象在 official-aligned 下全部存活：exec oracle gap +9.3/+8.5pp（full-doc/structured）；case-only 43/30、strategy-only 31/23；naive both 干扰 31/29。
- 新发现：corrected 指标下 structured_case −7.7pp，机制=案例 exe_ans 小数值与 structured prompt 的"return a percentage"规范冲突（尺度污染）。exec 指标不受影响且 case 正向。
- reproduction 排名仍未复现论文（Mem0-Aug>Baseline>Structured>RAG），模型能力依赖，非 pipeline 错误。
- **判定 READY FOR STAGE 3**。约束：注入尺度一致性、grounding 配置化、grounding/experience 检索独立。
