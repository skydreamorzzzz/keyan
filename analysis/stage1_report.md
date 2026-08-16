# Stage 1 可行性分析：FinQA × Agent Memory（Case / Strategy）

> 数据来源：官方仓库 `czyssrs/FinQA`（EMNLP 2021）`dataset/` 目录。
> 全部结论基于**实际下载的数据**（train/dev/test/private_test 均已校验与 GitHub blob SHA 一致），非论文转述。

---

## 1. FinQA 实际数据结构

### 1.1 文件与规模

| 文件 | 样本数 | 是否有 gold |
|---|---|---|
| train.json | 6251 | 完整（question/program/steps/gold_inds/exe_ans…） |
| dev.json | 883 | 完整 |
| test.json | 1147 | 完整 |
| private_test.json | 919 | **仅 question**（无任何 reference） |

### 1.2 字段结构（train/dev/test 一致）

**顶层字段**
- `id`：形如 `ADI/2009/page_49.pdf-1`，即「报告路径 + 该报告内问题序号」。
- `pre_text` / `post_text`：表格前/后的句子列表（tokenized，含大量噪声与空句）。
- `table`：`list[list[str]]`，row[0] 为表头；单元格常含 `-36 ( 36 )`、`22% ( 22 % )`、`2014`（实为 `—` 的解析伪影）等噪声格式。
- `qa`：
  - `question`：问题文本（tokenized）。
  - `program`：线性推理程序，**字符串**，如 `"divide(100, 100), divide(3.8, #0)"`。
  - `program_re`：嵌套表达式**字符串**，如 `"divide(3.8, divide(100, 100))"`。
  - `gold_inds`：`dict`，`{"text_N": "<句子>", "table_N": "<行渲染文本>"}`——gold 支持事实。`text_N` 索引 `pre_text+post_text` 拼接后；`table_N` 索引 table 行（row0=表头）。
  - `steps`：`list[{op, arg1, arg2, res}]`——带**中间结果**的执行轨迹（100% 填充）。
  - `exe_ans`：gold 程序执行结果，98% 数值、2% `yes/no`。
  - `answer`：99% 填充但**不可靠**（见 §2）；`explanation`：仅 15.6% 填充（部分有高质量自然语言解释）。
  - `ann_table_rows` / `ann_text_rows`：gold 行/句索引，但**覆盖率不完整**（69.4% / 34.8%），个别样本有 gold_inds 却无 ann_*。
  - `tfidftopn` / `model_input`：检索预处理伪影。
- `table_retrieved` / `text_retrieved` / `table_retrieved_all` / `text_retrieved_all`：**retriever 模型输出**（带 score），非 gold，且官方 README 明确其训练曾存在 label-leak bug（2022-05-04 修复说明）。

### 1.3 程序解析（官方 evaluate.py 语义）
- 每步 4 token：`op(`、`arg1`、`arg2`、`)`；10 个算子：`add/subtract/multiply/divide/exp/greater/table_max/table_min/table_sum/table_average`。
- 参数可为字面数字、`const_*`（`const_1000`=1000 等）、或 `#N` 引用前步结果。
- 训练集算子频次：divide 4432、subtract 2735、add 1517、multiply 575、greater 124、table_* 206、exp 5。
- 14.4% 程序含 `const_*`（单位换算：const_1000 / const_1000000 / const_100 最常见）。

### 1.4 报告共享与跨 split
- **92% 的报告承载 >1 个问题**（最多 6 个）；同报告内问题对平均 Jaccard=0.32（19% 对 >0.5）。
- **跨 split 报告零重叠**（train/dev/test 两两共享报告=0）。
- **但公司高度重叠：test 100 家公司中有 99 家在 train 出现**（train↔test 共享公司 99）。
- train↔dev / train↔test 完全重复的问题占比 1.81% / 0.61%（低但非零）。

---

## 2. 20 条抽样观察总结

分层抽样覆盖：1 步（divide/subtract/add/multiply/table_average/table_sum/table_max）、2 步、3 步、≥4 步、unit-scaling、comparison(yes/no)、exp 复利、纯文本推理、单位换算。

**可分性良好的样本（占大多数）**
| 样本 | 问题 | gold 程序 | 可抽象策略 |
|---|---|---|---|
| RL/2012 | X 占总数比例 | divide(part,total) | X 是 Y 的 % = X/Y |
| BLL/2010 | 2009→2010 变动 | divide(sub(new,old),old) | %change=(new-old)/old |
| BLK/2017 | AUM 增幅 | subtract(divide(new,old),const_1) | %change=new/old−1（等价形式） |
| ALLE/2016 | 平均 revenue | table_average(2016) | 行内跨列平均 |
| APD/2013 | 欧元债到期值 | multiply(397, exp(add(1,2%),7)) | 复利 FV=P(1+r)^n |
| AMT/2012 | 年摊销额 | divide(add(75,72.7),20) | 直线摊销=成本/年限 |
| JPM/2012 | 达标缺口 | subtract(multiply(RWA,9.5%),tier1) | 资本缺口=目标−当前 |
| LMT/2010 | 经营费用增速 | divide(sub(sub(NS,OP)_10, sub(NS,OP)_09), …) | 经营费用=营收−营业利润（复合指标） |
| AMAT/2016 | 土地总面积 | add(mul(280,43560), mul(7041,const_1000)) | 单位换算+千→单位 |

**结构噪声/可分性差的样本**
- **PNC/2011**：问题句义混乱（"what was the ratio of the total…"），程序却做 `add(130,294)=424`，而 `answer` 字段为 44.2%（=130/294 的 ratio）——**问题、程序、answer 三方不一致**。
- **GPN/2008**：程序 `subtract(8.1, const_1000)` 按官方执行器得 −1.34769（金融上错误），但 `steps.res` 与 `answer` 字段为 11.01（正确的 8100/736）——**program 与 steps 的 const 语义不一致，gold 程序存在标注 bug**。
- **HWM/2016**：程序 `subtract(multiply(divide(970,100),100),100)` 绕过 `/100×100`，结构低效但值正确。
- **gold_inds 过度包含**：MMM/2007 的 text_14、PKG/2011 的 text_99 与计算无关，属多余支持事实。
- **exe_ans 尺度不一致**：同为百分比，F_subdiv 的 exe_ans=0.02409（小数），C_mulc 的 exe_ans=17.98（×100 的百分数）——需按算子类别理解尺度。
- **`answer` 字段与 exe_ans 大面积不一致**：600 条抽查中与 exe_ans 精确相等仅 ~26%，7% 差 100×，其余受舍入/格式/标注差异影响——**评估一律用官方 evaluate.py 的 execution / program accuracy，勿用 `answer` 字段做 target**。

**关键结论**：FinQA 大多数样本能清晰拆出「具体案例」（公司/报告/表/实体/数值）与「可复用策略」（运算结构+角色绑定）。噪声样本占比不高但真实存在，Strategy Memory 必须显式记录这些坑。

---

## 3. Case / Strategy Memory 可分性判断

**结论：可行，但需严格定义边界，否则两者会塌缩成同一个东西。**

- **抽象轴已经由官方 eval 给出**：`equal_program` 把字面数字/表行映射为符号变量（a0, a1…）比较程序等价性——这正是「策略抽象」的天然定义：**策略 = 去除具体值的符号程序 + 变量角色语义**。
- **建议的定义边界**：
  - **Case Memory**：保留具体性的记忆。字段含报告上下文、表格切片、实体名、具体数值、gold 事实、程序、执行轨迹、结果。用途：检索相似案例→类比迁移。
  - **Strategy Memory**：只存抽象模板 + 角色绑定 + 单位约定 + 语义名，**不含任何具体数值、公司名、实体名、年份**。用途：跨案例的方法迁移。
  - **判别准则**：一条记忆若移走具体数值后信息量不减，它就是 Strategy；若抽走数值就失去检索价值，它就是 Case。
- **重叠风险**：若 Strategy 残留数值/实体名（常见于 LLM 生成的模板里带示例），或 Case 只留程序形状，两者会重复。**建议 Strategy 的模板用 slot（#1,#2）表示，example_cases 单独作为链接字段**，避免把具体值写进模板本体。
- **是否主要依据 gold program 构造 Strategy**：是，但必须做两层处理：(1) 符号化（数字→slot）；(2) 语义化（LLM 生成角色绑定："哪个是 new/old、part/whole、本金/利率/期数"，并标注单位与尺度约定）。纯 program 形状不够——F_subdiv 与 BLK/2017 是同一语义（%change）两种形状；D_4p 需要领域知识（经营费用=营收−营业利润）才能解释程序。
- **Case Memory 保留多少原始 context**：第一版建议保留「gold_inds 对应的事实切片 + 相关表行 + 表头」，可再加完整 pre/post/table 作为可选项。不保留 `table_retrieved` 等模型输出。

---

## 4. 数据泄漏风险

| 风险 | 现状 | 处置 |
|---|---|---|
| 同报告跨 split 泄漏 | **0**（split 间报告零重叠） | 结构上已免疫 |
| 同公司跨 split | **test 99/100 公司在 train** | 这是最大 confound：内存检索几乎必命中同公司案例。**必须把增益拆成「同公司」vs「异公司」**，否则无法区分「记忆真的有用」还是「公司模板迁移」。可视为研究点而非纯 bug |
| 完全相同问题跨 split | train↔test 0.61% | 过滤后评估 |
| 官方 retriever label-leak bug | `table_retrieved*`/`model_input`/`tfidftopn` 由带 bug 的模型产出 | **内存构造一律禁用这些字段**，只用 gold 事实 |
| `answer`/`steps` 字段 | 与 program/exe_ans 存在不一致 | 不用作 target；steps 仅作策略参考并记录 caveat |
| 同报告兄弟问题 | 92% 报告>1 题，同报告问题相似度高 | Case Memory 检索需按报告去重/屏蔽，避免「背答案」假象；同时报告「屏蔽同报告」后的增益 |

**实验设计是否合理（train 构造 memory、test 作 query）**：合理且是 FinQA 标准做法，但必须：(1) 内存只含 train；(2) 报告级与公司级 confound 分析；(3) 官方 evaluate.py 指标。

---

## 5. 第一版 Memory Schema

### Case Memory（每条 = 一个 train 样本）
| 字段 | 来源 | 说明 |
|---|---|---|
| case_id | 原数据 | id |
| report / company / fiscal_year | 从 id 提取 | 如 `RL/2012/page_13.pdf` → RL, 2012 |
| question | 原数据 | 原样 |
| problem_kind | LLM 标注 | 问题类型（ratio/percent_change/table_aggregation/compound_interest/shortfall/comparison/unit_conversion…） |
| gold_facts | 原数据 `gold_inds` | 渲染后的事实文本（text/table） |
| context_slice | 原数据派生 | gold 事实对应的句子/表行 + 表头 + 单位行（可选加完整 pre/post/table） |
| program / program_re | 原数据 | 线性 + 嵌套 |
| steps | 原数据 | 带中间值的轨迹（记录 res 单位） |
| exe_ans | 原数据 | 官方 target |
| answer / explanation | 原数据 | 仅参考；标注不可靠 |
| strategy_ref | 派生 | 关联 Strategy id（可选，去重用） |

### Strategy Memory（每条 = 从若干案例抽象的策略）
| 字段 | 来源 | 说明 |
|---|---|---|
| strategy_id | 派生 | 唯一 id |
| name | **LLM 抽象** | 语义名，如「百分比变动 (new−old)/old」 |
| problem_type | **LLM 抽象** | 归类 |
| template | **LLM 抽象** | slot 化符号程序，如 `divide(sub(#1,#2),#2)`；需与官方 equal_program 符号化一致 |
| role_bindings | **LLM 抽象** | 槽位语义（#1=new,#2=old …） |
| units_convention | **LLM 抽象** | 答案尺度（小数 vs ×100）、单位（thousands/millions）、const 用法 |
| canonical_formula | **LLM 抽象** | 人类可读公式 |
| caveats | **LLM 抽象** | 已知坑（const 伪影、gold_inds 过包含、尺度歧义） |
| example_cases | 派生 | 1–3 个 case_id 锚定 |
| confidence | LLM | 供人工 QC 排序 |

**直接来自原数据**：question、context_slice、gold_facts、program、program_re、steps、exe_ans。
**需 LLM 抽象生成**：problem_kind、strategy name/template/role_bindings/units_convention/caveats。
**禁止进入 Strategy**：具体数值、公司/报告名、实体名（如 "performance plans"）、年份、表单元格原文、答案值。

### 人工质检（小规模，不必批量）
1. 抽 50–100 条 Strategy（按 confidence 排序 + 按 problem_type 分层）。
2. 逐条核对：(a) template 用官方执行器跑通且与原 program 符号等价；(b) role_bindings 语义正确；(c) 无泄漏具体值/实体；(d) units_convention 标注正确。
3. 对照 20 条人工分析样例复核 problem_kind 标注一致性。

### 防泄漏清单
- Memory 只从 train（6251）构造；dev/test/private_test 仅作 query。
- 完全重复问题（train↔dev/test）在评估集中剔除。
- 检索时按报告屏蔽（若测试一个报告的问题，不检索同报告 train 案例）。
- 所有结论报告「同公司 vs 异公司」与「屏蔽报告」两个视图。

---

## 6. 下一步最小实验

**Pilot（先不碰全量生成）**
1. **Case Memory**：train 全量 6251 条——字段全部来自原数据，无 LLM 成本，直接入库。
2. **Strategy Memory**：从 train 分层抽 ~200 条，LLM 生成策略 + 上述人工 QC（产出第一版策略库与坑清单）。
3. **评测集**：dev 883 条（test 完全冻结）。
4. **四臂对照**（同一强 LLM、统一 prompt 模板）：no-memory / case-only / strategy-only / case+strategy。
5. **检索**：先用现有 embedding（bge/sentence-transformers 环境已具备）做 top-k 稠密检索；Case 按 question+problem_kind，Strategy 按 problem_kind+question。
6. **指标**：官方 evaluate.py 的 execution acc 与 program acc；按 problem_type 分层报告；并报告「同公司 vs 异公司」「屏蔽同报告」两个消融。
7. **关键判读点**（回应四个研究问题）：
   - case-only vs no-memory 是否显著↑（Q1）；
   - strategy-only vs no-memory 是否显著↑（Q2）；
   - 按 problem_type 分层看增益差异（Q3）；
   - case+strategy vs 各自单独 是否有增量（Q4，不预设一定互补）。

**替代方案与取舍**
- 用 dev 做检索库的候补：不可，dev 必须留作评测。
- 用 `program_re` 而非 `program` 构造策略：可以但会丢中间步；第一版同时保留。
- 用 text 检索而非 embedding：第一步 embedding 足够，后续可加 BM25 混合。

---

## 附：已产生的检查脚本（`analysis/` 目录）
- `00_inspect_finqa.py`：split 规模/字段/report 共享/跨 split 重叠/算子频次。
- `01_deep_inspect.py`：字段类型、gold_inds 语义、retrieved 字段、program 可解析性。
- `02_field_quality.py`：填充率、索引语义校验、问题类型、exe_ans 类型、const 统计。
- `03_stratify.py`：按程序结构分层（bucket 及 struct 分布）。
- `04/05_sample20*.py`：确定性 20 条抽样。
- `sample20_readable.txt` / `sample20_dump.json`：20 条完整上下文，供人工复核。
- `official_code/`：官方 evaluate.py 与 finqa_utils.py。
