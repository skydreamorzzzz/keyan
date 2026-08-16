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

## 11. Stage 3 Validity / Stability Audit（2026-08-16）

### evaluator 修正
- `pilot/executor.py` 的主 `match_result` 改为 official-compatible execution equality：数值 `round(x, 5)` 后精确相等，字符串按原值相等；旧 relative tolerance 保留为 `match_result_legacy` 仅诊断用。
- 同时修复官方 linear program 解析：无 `#` 但存在顶层逗号分隔步骤的程序现在按顺序执行，避免只执行第一步。
- 测试：`python -m unittest pilot.tests.test_executor_official` 通过；dev 883/883、train 6251/6251 gold program 与官方 evaluator 一致。

### Stage 2 strict 重算
- Full-doc strict：None 0.6809，Case 0.7175，Strategy 0.6931，Both 0.7256；Best Fixed 0.7256，Oracle 0.8191，Gap 0.0935。
- 相比旧 relative-tolerance 标签：Best Fixed 0.7276 -> 0.7256，Oracle 0.8211 -> 0.8191；Oracle Gap 不变。
- Structured strict：None 0.6220，Case 0.6443，Strategy 0.6301，Both 0.6545；Best Fixed 0.6545，Oracle 0.7378，Gap 0.0833。

### provenance 修正
- `pilot/stage2_official/run_official.py` cache key 从 `prompt[:300]` 改为完整 system prompt + 完整 user prompt + mode/arm/sample index/model/config/version 的 SHA-256。
- stability experiment 使用独立 cache namespace：`pilot/stage3/stability/llm_cache_stability_<replicate>.jsonl`，不复用 Stage 2 旧 cache。
- 限制：历史 Stage 2 replicate 的原 cache key 弱，保留为 historical run；新 r1/r2 使用当前可用 DeepSeek official API fallback (`deepseek-chat`, temperature 0)，不是完全相同的旧 Anthropic-compatible `DeepSeek-V4-flash[1m]` backend。

### repeated-run stability
- 固定 Full-doc official-aligned，official dev[:492] 中用 label-independent SHA-256 deterministic 规则选 250 条；四臂 None/Case/Strategy/Both 新跑 r1/r2，共 2000 次新 LLM 调用，failures=0。
- 3 replicates（stage2_old+r1+r2）上 per-arm correctness agreement：None 0.9387，Case 0.9547，Strategy 0.9360，Both 0.9627。
- repeated expected：Best Fixed 0.7467，Oracle 0.8347，Gap 0.0880；subset one-shot gaps 为 0.084/0.088/0.092。
- cross-run preference transfer：用两个 runs 判断 query-level arm preference，在 held-out run 平均 accuracy 0.8173；held-out Best Fixed 平均 0.7467；delta +0.0707，约回收 repeated expected gap 的 80%。
- 结论：oracle gap 不像主要由 one-shot run noise 造成，存在稳定可迁移 marginal utility heterogeneity。

### leakage / duplicate robustness
- report-grouped CV audit：strict random KFold 最好 0.7500（query_retrieval_meta/logreg），GroupKFold by report 最好 0.7317（query_retrieval_meta/rf）。此前 Stage 3 selector 数字需按 GroupKFold 从严解释。
- exact duplicate train-question audit：official dev[:492] 中 9 条 exact duplicate；去掉后 Case gain vs None 为 +3.73pp（全量 +3.66pp），Oracle Gap 为 9.52pp（全量 9.35pp）。duplicates 不解释 Case 增益或 oracle gap。

### 判定
- **PROCEED TO MARGINAL-UTILITY SELECTOR**。
- 下一轮必须以 strict official labels、report-grouped CV、repeated-run stability/transfer 为主评价；不要沿用 random KFold 的乐观 selector 结论。

## 12. Runtime-Normalized Stability Final Audit（2026-08-16）

### runtime identity 修正
- 上一轮把 `DeepSeek-V4-flash[1m]`/Anthropic-compatible 与 `deepseek-chat`/OpenAI-compatible 表述为不同模型过强。DeepSeek 官方 V4 文档说明：过渡期 `deepseek-chat` 指向 `deepseek-v4-flash` non-thinking mode。
- 但历史 artifact 没保存 response-level `model`/`system_fingerprint`：`stage2_old`、`r1`、`r2` 均标注为 provenance insufficient，不能作为 strict same-runtime replicates。
- 因此只补最小严格实验：固定原 250-query subset，新跑 `rn1/rn2/rn3`，不扩大到 492，不改 retrieval/memory/prompt。

### provenance / cache
- `pilot/llm.py` 默认 DeepSeek official fallback 改为请求 `deepseek-v4-flash`，显式 non-thinking，新增 `call_once_with_metadata` 保存 response model/fingerprint。
- `pilot/stage3/stability_run.py` cache version 升为 runtime-normalized v2；cache key 包含 runtime、endpoint、requested/effective model 可验证字段、thinking mode、temperature、max_tokens、完整 prompt、arm/mode/sample、retrieval config、memory config。
- `pilot/stage2_official/run_official.py` 也加入 runtime/retrieval/memory config 到后续 cache key，避免未来混用。
- `rn1/rn2/rn3` 三轮 3000 calls 均返回：requested/effective/response model = `deepseek-v4-flash`，system_fingerprint = `a26a7955944dc5c60445bff77fac9c8e`，thinking=false，temperature=0，max_tokens=600。

### selector leakage 修正
- `run_selector_baselines.py` 修复 fold prior leakage：tie-breaking priors 只由 `train_idx` 计算；random CV 改为 seed KFold，避免用全数据 preferred label 做 stratification。
- no-leak selector audit：random best 0.7378（+1.22pp），report GroupKFold best 0.7317（+0.61pp）。旧 query/retrieval selector 仍弱，不作为下一阶段方法。

### normalized stability 结果
- Same-runtime arm agreement：None 0.9787，Case 0.9920，Strategy 0.9840，Both 0.9920。
- Expected metrics：Best Fixed 0.7467，Oracle 0.8387，Oracle Gap 0.0920。
- Preference event repeatability：
  - Case>Strategy：26 any，23 >=2/3，19 3/3。
  - Strategy>Case：21 any，20 >=2/3，19 3/3。
  - Case>Both：6 any，5 >=2/3，5 3/3。
  - Strategy>Both：12 any，12 >=2/3，10 3/3。
- Three-way held-out transfer：
  - rn2+rn3→rn1：policy 0.832 vs Best Fixed 0.748，gain +0.084，95% bootstrap CI [0.052, 0.120]。
  - rn1+rn3→rn2：policy 0.836 vs 0.744，gain +0.092，CI [0.056, 0.132]。
  - rn1+rn2→rn3：policy 0.840 vs 0.748，gain +0.092，CI [0.056, 0.132]。
  - mean gain +0.0893；pooled CI [0.0693, 0.1093]，pooled 仅作汇总，fold-level CI 为主。

### 判定
- **PROCEED TO MARGINAL-UTILITY SELECTOR**。
- 下一阶段方向：Both as default action + estimate Case/Strategy/None relative marginal utility + confidence gating。
- 不再主推 four-arm independent correctness classification。

## 13. Stage 4A Marginal-Utility Learnability Audit（2026-08-16）

### framing 修正
- 上一轮 +8.9pp held-out transfer 是 **same-query repeated-history ceiling**：用同一 query 前两轮真实 correctness 预测第三轮 preference。不能当 unseen-query selector 性能。
- Stage 4A 改为 annual-report grouped unseen-query/new-report 泛化：default=Both，只预测 `{None, Case, Strategy}` 相对 Both 的 marginal utility。

### target
- `delta_a = mean_r[correct(a)-correct(Both)]`，主 repeated target 用 `rn1/rn2/rn3`。
- 同时保存 `gain_a=P(a correct & Both wrong)`、`harm_a=P(a wrong & Both correct)`、`net_utility=gain-harm`。
- 不再把 arm 本身 correctness 当核心 target。

### grouping / support
- 新增 `annual_report_group=COMPANY/YEAR`，主结果用 annual-report GroupKFold；`page_group=COMPANY/YEAR/page_x.pdf` 仅 secondary。
- n=250，annual groups=158，page groups=187。
- Deviation support 稀疏但不集中：任意 deviation 24/250，覆盖 22 annual reports。
  - None>Both：18 any，18 >=2/3，17 3/3。
  - Case>Both：6 any，5 >=2/3，5 3/3。
  - Strategy>Both：12 any，12 >=2/3，10 3/3。

### synthetic mechanism features
- 生成 250 条 fixed-schema LLM features；只给 question/context/retrieved cases/retrieved strategies，不给 correctness/gold answer/gold program/oracle/gold operation。
- runtime 固定 `deepseek-v4-flash`，fingerprint `a26a7955944dc5c60445bff77fac9c8e`，temperature 0；cache key 含完整输入/schema/runtime。
- feature groups：scale、compatibility、interaction。该设计是 exploratory，来自 Stage 3/3.1 failure modes（scale pollution、memory conflict），后续需外部 holdout confirm。

### leakage controls
- outer annual-report GroupKFold。
- inner grouped CV 只在 train fold 选 threshold/lambda。
- train fold 外 statistics 不参与 prediction/tie-breaking/threshold。
- paired bootstrap 主用 annual-report cluster bootstrap；query-level bootstrap 只 secondary。

### 结果
- Always Both expected accuracy：0.7467；Oracle：0.8387；gap：0.0920。
- Existing features best：`existing_meta/delta/ridge`，0.7507，+0.4pp，cluster CI [-1.13pp, +2.01pp]。
- Best overall：`existing_meta + compatibility / delta ridge`，0.7640，+1.73pp，gap recovery 18.8%，coverage 20.8%，beneficial deviations 8，harmful 4，cluster CI [-0.92pp, +4.49pp]，query CI [-0.67pp, +4.40pp]。
- Best gain/harm：`synthetic interaction / logreg`，0.7560，+0.93pp，harm rate 1.5%，cluster CI [-0.38pp, +2.49pp]。
- Page-group secondary best：0.7560，+0.93pp；不作为主 claim。

### 判定
- **WEAK BUT PROMISING — IMPROVE OBSERVABILITY**。
- stable heterogeneity 已存在，但当前 inference-time observable state 对 unseen annual reports 只有弱预测力；还不能进入正式 method development。
- 下一步应增强 retrieved-content compatibility observability：operand-role alignment、scale/unit verification、case/strategy operation consistency，以及更严格 confidence gate。

## 14. Stage 4B Conservative Router Freeze & Confirmatory Holdout（2026-08-16）

### protocol hardening
- 新增 `pilot/stage4b/`，主 grouping 固定为 `annual_report_group=COMPANY/YEAR`；page-level grouping 不作为主结果。
- 修复 Stage 4A 协议风险：`DictVectorizer`/preprocessing 只在 outer-train fold 内 fit；outer GroupKFold 仅用于最终 OOF；inner grouped CV 负责 feature set、formulation、model、threshold、lambda 全部选择。
- confidence gate tie-breaking 改成保守规则：utility 相同或 one-standard-error 内接近最佳时，优先低 coverage、高 threshold、高 harm penalty、高 abstention；原则为不确定即 Both。
- `pilot/stage3/stability_run.py` 增加 run-level runtime guard：同一 cache namespace 内若 response model / fingerprint / runtime config 漂移，则停止而非混合。

### fully nested development result
- 250-query runtime-normalized development subset 上，fully nested annual-report GroupKFold OOF policy 选择 0 个 deviation，等同 Always Both。
- Expected accuracy：Always Both 0.7467，fully nested policy 0.7467，Oracle 0.8387；gain vs Both 0.0000，Oracle Gap Recovery 0.0%，annual-report cluster CI [0.0000, 0.0000]。
- realized single-run evaluation：rn1/rn2/rn3 policy accuracy 分别 0.7480/0.7440/0.7480，与 Both 完全相同；mean gain 0.0。

### hierarchical router audit
- 固定候选 audit 仅作 exploratory，不用于 freeze：
  - flat delta + compatibility：0.7507，+0.40pp，coverage 2.4%，CI [-0.55pp, +1.61pp]。
  - hierarchical + compatibility：0.7360，-1.07pp，coverage 9.6%。
  - hierarchical + synthetic interaction：0.7560，+0.93pp，coverage 4.4%，CI [-0.38pp, +2.48pp]。
  - gain/harm + synthetic interaction：0.7467，+0.00pp。
- hierarchical architecture 目前没有稳定优于旧 marginal heads；正向结果仍跨 0，且不能作为 confirmatory claim。

### frozen router / holdout
- 冻结 router：`conservative_no_override_router`，配置见 `pilot/stage4b/stage4b_frozen_router_config.json`，规范见 `pilot/stage4b/FROZEN_ROUTER_SPEC.md`。
- frozen policy 明确为 Always Both；holdout 结果不得用于重新启用 deviation 或修改 threshold/feature/model。
- fresh holdout 使用 `data/finqa/test.json` 中 annual report 同时 disjoint from train.json 和 dev[:492] 的 primary subset：97 queries，33 annual reports。private_test 无 executable gold label，不用于 accuracy。
- holdout 两轮 confirmatory execution 只跑 Both（frozen router coverage 0）：h1 0.7526，h2 0.7629；router gain 均 0.0000，cluster CI 均 [0.0000, 0.0000]。
- runtime provenance：DeepSeek official API，requested/effective/response model `deepseek-v4-flash`，non-thinking，temperature 0，max_tokens 600，fingerprint `a26a7955944dc5c60445bff77fac9c8e`。
- API 使用：194 次 Both execution calls；0 次 selected deviation calls；0 次 holdout synthetic feature calls。

### accuracy-memory tradeoff
- development Pareto：None 0.6933 / 0 memory tokens；Strategy 0.7053 / 209 tokens；Case 0.7160 / 413 tokens；Both 0.7467 / 623 tokens；frozen router 0.7467 / 623 tokens。
- holdout token estimate：Both/frozen router 平均 prompt tokens 1275.2，memory tokens 611.4；没有 memory-cost reduction。

### 判定
- **DEVELOPMENT SIGNAL DID NOT REPLICATE**。
- Stage 4B 不否定 fixed-runtime marginal-utility heterogeneity；它否定的是“当前 Stage 4A inference-safe features/model-search 已足以冻结一个 conservative unseen-query router”的更强 claim。
- 下一步不要继续在同一 250 条上调分；应先提高 observable state：retrieved-content reasoning、operand-role verification、scale/unit consistency、Case/Strategy conflict modeling，然后预注册新 router 并在新 holdout 上确认。

## 15. Stage 4B.1 Protocol Repair & Re-audit（2026-08-16）

### 修复项
- 修复 `evaluate_realized_by_replicate()`：不再用 `statistics.mean(np.array(...))`；改为显式 float numpy array，并保证 `gain_vs_both = policy_accuracy - both_accuracy`，同时保存 paired diagnostic。
- 修复 inner-CV selection：不再对 absolute accuracy 做 one-SE；每个 inner fold 计算 paired gain over Always Both，并基于 mean gain / SE 做 conservative one-SE。
- 显式加入 `Always Both` candidate（gain=0, coverage=0）；不确定时优先 Both。
- 修复 hierarchical Case gate：Case confidence 不足时直接 abstain 到 Both，不再自动换成第二名 deviation arm。
- 加固 cache provenance：旧 cache 加载时验证所有 runtime/fingerprint；cache hit 也验证；缺 provenance 或 drift 直接 fail。
- 新增测试：`pilot/tests/test_stage4b_protocol.py` 覆盖 realized gain、conservative selection、Case abstention、cache runtime drift。

### re-audit 结果
- 未调用 API，未新增 feature，未扩大模型/threshold/lambda 搜索空间；只用现有 `rn1/rn2/rn3`。
- corrected fully nested annual-report OOF：
  - Always Both 0.7467；nested policy 0.7520；expected gain +0.53pp；Oracle Gap Recovery 5.8%。
  - deviation coverage 5.6%（14/250）：Both 236、None 8、Case 5、Strategy 1。
  - beneficial/harmful/neutral deviations：2 / 1 / 11。
  - annual-report cluster CI [-0.54pp, +1.92pp]，仍跨 0。
- corrected realized gain：
  - rn1：0.7560 vs Both 0.7480，+0.80pp。
  - rn2：0.7480 vs Both 0.7440，+0.40pp。
  - rn3：0.7520 vs Both 0.7480，+0.40pp。
- fixed candidate audit（均与 explicit Both candidate 竞争）：
  - flat delta + compatibility：-0.67pp，CI [-2.56pp, +0.83pp]。
  - hierarchical + compatibility：+0.00pp，CI [-1.17pp, +1.21pp]。
  - hierarchical + synthetic interaction：-0.27pp，CI [-0.84pp, +0.00pp]。
  - gain/harm + synthetic interaction：+0.13pp，CI [-0.79pp, +1.17pp]。

### 判定
- **SIGNAL SURVIVES BUT NOT CONFIRMED**。
- Stage 4B 的 “collapse to Both” 结论部分来自协议 artifact；修复后 fully nested policy 出现小幅、跨 rn1/rn2/rn3 方向一致的正 gain。
- 但当前证据仍很弱：CI 跨 0，beneficial deviation 只有 2 个，多数 deviation 是 neutral，fixed candidates 没有稳定确认。
- 下一步不应把 +0.53pp 包装成 confirmed router；应在更好 observability 或明确 accuracy-memory objective 下做预注册确认。

## 16. Stage 4B.2 Router Stability & Accuracy-Memory Pareto Audit（2026-08-16）

### one-SE 修正
- 将 inner-CV `se()` 从 population std 改为 sample std：`np.std(vals, ddof=1) / sqrt(n)`。
- 未调用 API，未新增 feature，未扩大模型/参数/threshold/lambda 搜索空间。

### sensitivity
- Stage 4B.1 population-SE nested OOF：policy 0.7520，Both 0.7467，gain +0.53pp，coverage 5.6%，beneficial/harmful/neutral=2/1/11，CI [-0.54pp, +1.92pp]。
- Stage 4B.2 sample-SE nested OOF：policy 0.7440，Both 0.7467，gain -0.27pp，coverage 5.2%，beneficial/harmful/neutral=0/1/12，CI [-0.84pp, 0.00pp]。
- realized：rn1 0.7480 vs 0.7480 (+0.00pp)，rn2 0.7400 vs 0.7440 (-0.40pp)，rn3 0.7440 vs 0.7480 (-0.40pp)。

### router stability
- 5 个 outer folds 的 selected architecture：flat_delta 2，gain_harm 2，always_both 1。
- selected feature set：synthetic_interaction 4，none 1。
- thresholds：0.05/0.2/0.5/None 均出现；inner selected coverage=[0.1661, 0.0000, 0.0200, 0.0598, 0.0150]。
- 结论：nested OOF 是 model-selection procedure performance，不代表一个稳定单一 deployable router。

### accuracy-memory Pareto
- Always None：0.6933，avg memory 0.0 tokens，avg prompt 685.0。
- Always Strategy：0.7053，avg memory 209.3，avg prompt 894.3。
- Always Case：0.7160，avg memory 413.3，avg prompt 1098.3。
- Always Both：0.7467，avg memory 622.6，avg prompt 1307.6。
- sample-SE nested OOF：0.7440，avg memory 601.3，avg prompt 1286.2。
- 相比 Both：accuracy -0.27pp，memory/prompt 仅各省约 21.4 tokens；不是清晰 Pareto improvement。
- deviations 中 neutral 12 个，平均节省约 409 memory/prompt tokens；但 coverage 低，且 1 个 harmful deviation 也节省 token，因此 token saving alone 不能作为 correctness-preserving signal。

### deployable candidate freeze
- 全 250 development data 上用同样 conservative inner-CV procedure 选择 candidate，仅 freeze，不作 confirmatory claim。
- selected：flat_delta + existing_meta_plus_interaction，threshold 0.5，mean_gain +0.14pp，se_gain 0.58pp，coverage 3.2%。
- 新产物：`stage4b2_deployable_candidate_config.json`，`STAGE4B2_DEPLOYABLE_CANDIDATE_SPEC.md`。
- 旧 `stage4b_frozen_router_config.json` 已标记为 superseded historical artifact。

### 判定
- **SIGNAL DISAPPEARS UNDER SAMPLE-SE**。
- Stage 4B.1 的小正信号对 SE estimator 敏感；当前 Stage 4B feature/model/protocol stack 不应被视为可靠 router。
- 下一步不要继续在同一 250 条上调参；若继续，应转向预注册 efficiency objective 或更强 retrieved-content compatibility observability。

## 17. TAT-QA Case Memory + Retrieval Audit（2026-08-16）

### scope
- 只做 TAT-QA train-only Case Memory 与 retrieval-only dev audit；未调用 DeepSeek/任何 LLM，未构造 Strategy Memory，未跑四臂实验。
- 复用 FinQA pilot 的 dense retrieval 机制：`BAAI/bge-small-en-v1.5`，top-4，CPU，normalized embedding dot-product。

### implementation
- 新增 `pilot/multibench/tatqa_case_memory.py`。
- train Case Memory 保存到 `data/tatqa/processed/tatqa_case_memory_train.json`，共 13,215 条。
- 每条 case 保存 question、table、relevant paragraphs、answer type/source、scale、derivation、coarse operator、operator sequence、reasoning annotation、source_id。
- retrieval text 明确排除 answer、answer_type、answer_from、scale、derivation、operator、reasoning_annotation；target query retrieval text 只使用 inference-time 可见的 question、paragraphs、table。
- 检索增加 `source_id` exclusion，避免同源 table/report case 泄漏。

### retrieval-only audit
- 固定 dev 小样本：50 条，seed `20260816`。
- source leak count：0。
- 平均 top-1 cosine：0.9254。
- post-hoc diagnostic match rate（gold 字段只用于 audit，不参与 retrieval）：
  - answer_type：top1 0.740，any top4 0.980。
  - answer_from：top1 0.500，any top4 0.760。
  - operator：top1 0.640，any top4 0.900。
  - scale：top1 0.540，any top4 0.920。
- 产物：`pilot/multibench/output/tatqa/TATQA_CASE_RETRIEVAL_AUDIT.md` 与 `tatqa_case_retrieval_audit.json`。

### decision
- **READY FOR TAT-QA STRATEGY MEMORY DESIGN**。
- 风险：memory-side retrieval text 使用 train solved-case relevant paragraphs，而 target side 使用全可见 context，存在轻微表示不对称；`operator` 是 parser-derived coarse audit label，不是 TAT-QA 官方字段。
