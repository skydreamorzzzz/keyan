# Oracle Pilot 报告：Case vs Strategy 互补性与 Go/No-Go 判断

日期 2026-08-16。本报告回答 A–E 五个问题。全部实验细节与决策理由见 `DECISIONS.md`，代码在 `pilot/`，产物在 `pilot/output/`。

## 0. 实验设置（一句话版）

dev 分层抽样 **143 条**（配额偏重结构化类型），4 臂对照（no / case / strategy / both），模型 DeepSeek-V4-flash[1m]（temp 0），指标为**官方语义 execution accuracy**（执行器对 gold 自检 2000/2000 正确）。Case Memory = train 全量 6251 条原数据；Strategy Memory = 44 条 LLM 抽象（top-25 struct 覆盖 ~96%）；检索 = bge-small-en 稠密 top-k（case 4 / strategy 3）。

## 1. 主结果

### 1.1 四臂与 Oracle（execution accuracy，n=143）

| 指标 | no | case | strategy | both |
|---|---|---|---|---|
| exec acc | 0.5245 | **0.6224** | 0.5385 | 0.6154 |
| official round-5 | 0.4615 | 0.5804 | 0.4825 | 0.5664 |
| 结构模板匹配 | 0.4685 | 0.6434 | 0.4336 | 0.6364 |

- **Best Fixed = case（0.6224）**
- **Oracle = 0.7273**
- **Oracle Gap = +0.1049（+10.5pp）**

### 1.2 Contingency（Case/Strategy 正确性交叉）

| | Strategy 对 | Strategy 错 |
|---|---|---|
| **Case 对** | both_correct = **68** | case_only = **21** |
| **Case 错** | strategy_only = **9** | neither = **45** |

- Case 单独覆盖正确 68+21=89；Strategy 单独覆盖 68+9=77。
- **互补方向不对称**：case-only(21) 约为 strategy-only(9) 的 2.3 倍。
- case-only 集中在 **F_2step(8) / G_1step(6)**（常见"模板型"）；strategy-only 集中在 **A_comparison(3) / C_unitscaling(3) / D_multistep(2)**（"结构化/长链/比较"型）。

### 1.3 干扰（Both 臂）

- both 错但 case 或 strategy 对：**12 例**（8.4%）
- both 对但两单臂都错：2 例

→ **Both 臂（4 case + 3 strategy 简单拼接）达不到 Oracle（61.5% vs 72.7%），且主动负向干扰 12 例**。选择器不是"锦上添花"，而是必要机制。

### 1.4 分 bucket（exec acc，oracle）

| bucket | n | no | case | strategy | both | oracle |
|---|---|---|---|---|---|---|
| A comparison | 10 | **0.90** | 0.60 | 0.80 | 0.70 | 1.00 |
| B table_agg | 14 | 0.93 | **1.00** | 0.86 | **1.00** | 1.00 |
| C unitscaling | 18 | 0.167 | 0.278 | **0.333** | 0.333 | **0.556** |
| D multistep | 7 | 0.143 | 0.286 | 0.429 | **0.714** | **0.714** |
| E 3step | 12 | 0.083 | **0.25** | 0.167 | 0.25 | 0.25 |
| F 2step | 44 | 0.705 | **0.75** | 0.591 | 0.659 | 0.773 |
| G 1step | 38 | 0.447 | **0.684** | 0.526 | 0.632 | 0.737 |

- **C/D 是策略增益最明显的地方**（strategy 均 > no，且 D 的 both=oracle）。
- **A 桶 memory 有害**（no=0.90 > 各 memory 臂）：简单直接比较题上，memory 诱发过度推导（把 `greater(a,b)` 算成差值/比值）。
- **E 3step 全臂近地板**（oracle 0.25）：模型能力 / gold 标注限制，不是 memory 能救的。

### 1.5 retrieval-conditioned（关键 confound 视图）

| 条件 | n | no | case | strategy | both | oracle |
|---|---|---|---|---|---|---|
| strat 正确族被检索 | 47 | 0.638 | 0.702 | **0.766** | 0.787 | 0.830 |
| strat 正确族未检索 | 96 | 0.469 | 0.583 | **0.427** | 0.531 | 0.677 |
| case 同 struct 被检索 | 91 | 0.615 | **0.791** | 0.681 | 0.769 | 0.824 |
| case 同 struct 未检索 | 52 | 0.365 | **0.327** | 0.288 | 0.346 | 0.558 |

→ **Strategy 的增益完全取决于是否检索到正确策略族**：命中时 +12.8pp，未命中时 −4.2pp（反噬）。Case 同理：同 struct 命中 +17.6pp，未命中 −3.8pp。**当前 strategy 检索精确族命中率仅 32.9%**（case 同 struct 63.6%）。

### 1.6 自然分布加权

按 train bucket 自然比例加权：**best fixed ≈ 0.694，oracle ≈ 0.744，Oracle Gap ≈ 0.05（5pp）**。
分层样本（10.5pp）> 自然分布（5pp）：gap 真实存在，但幅度对采样敏感（分层过度采样了难类型）。

## 2. A. 核心假设：Case 和 Strategy 存在明显互补吗？

**结论：存在，但不对称。**

- 30/143（21%）的题目恰好只有一种 Memory 正确（case-only 21 + strategy-only 9）。
- 分 bucket 看互补方向清晰：**Case 主导"常见模板型"（1–2 步、占比/变化/单价），Strategy 主导"结构化型"（比较、单位换算、长链、跨年聚合）**。
- 但 Strategy 的整体增益小（+1.4pp），且完全受检索与变体质量制约（见 D）。

## 3. B. Oracle Gap 有多大？值得做 adaptive selection 吗？

- 分层样本：**10.5pp**（相对 best fixed 提升 ~17%）；自然分布加权：**~5pp**。
- gap 主要来源：C unitscaling（oracle−best ≈ 22pp）、G 1step（≈5pp）、A comparison（≈10pp）、F 2step（≈2pp）；D multistep 里 both 已到 oracle。
- **判断：gap 明显到足以支撑研究，但不足以支撑"必然大幅提升"的预期。** 更重要的信号是 **Both 拼接的负干扰（12 例）**——它说明"该用哪种记忆"本身是真实问题，selection 不是可有可无。**值得继续，但要基于修正 confound 后的更干净设定重新验证幅度。**

## 4. C. 为什么互补？（来自实际 failure cases，非直觉）

**Case 赢的机制 = 模板模仿。** 检索到结构几乎相同的真实案例时，模型直接照抄正确形状：
- C/2017 累计收益比 ← 检索到 C/2016 同款 `divide(subtract(208.1,const_100), subtract(193.5,const_100))`（同公司同表段）。
- AMT 每塔成本 ← AMT 收购"cost per tower"同款 `divide(multiply(173.2,const_1000000),962)`。
- PPG 公司匹配额 ← 检索到 AMT/2014 **完全相同**程序 `subtract(multiply(75%,6%),multiply(50%,6%))`。
- AON table_min ← 案例展示了正确**行标签拼写**（`table_min(segment operating income margin,none)`，无记忆臂写成 `row3`）。

**Strategy 赢的机制 = 结构消歧。** 当相邻案例结构相似但不相同、会误导时，抽象策略给出正确骨架：
- CDNS/LKQ 累计收益**差** ← S027；案例只提供单个收益（模型欠推导）。
- AES/2015、JPM/2018 跨年**平均** ← S016（sum÷count）；案例诱导 `table_average(row)` 或 2 值平均（行标签/数量错误）。
- AES/2002、PNC/2009、UNP/2011 直接**比较** ← S015；案例诱发把 `greater(a,b)` 展开成差值。

**干扰机制 = 上下文污染。** Both 臂把 case 数值与 strategy 形状混用：
- JPM/2018 both 抄了检索案例里**别的年份**的数字（226892/219345/203449 ≠ gold 228681/200247/236670）。
- LMT/2010 both 把 case 的 cash 数字套进 strategy 的 percent-change 形状。
- PNC/2018 both 采纳了 strategy 的 ×100 变体（gold 要小数）。

**A 桶 memory 有害 = 过度推导偏置。** 简单 `greater(a,b)` 题给记忆后，模型倾向把比较改成差值/占比。

## 5. D. 当前最大 confound

1. **Strategy retrieval 质量（最大）**：正确族命中仅 32.9%；未命中时 strategy 反噬（−4.2pp）。当前测量的 strategy 增益是**下界**，不能作为"strategy 无用"的证据，也不能作为"strategy 强大"的证据。
2. **Strategy 变体/尺度歧义**：percentage_change 有 fraction 与 ×100 两种合法变体（S002 vs S022），模型常跟随错的变体被计错——这是 Strategy **定义质量**问题，不是检索问题，也不全是模型问题。
3. **公司/模板重叠**：100 家公司 99 家在 train；case 记忆可能大量在吃"公司模板惯例"，而非"跨案例推理迁移"。需公司条件化消融（后续）。
4. **模型能力**：E_3step 全臂 oracle 仅 0.25；记忆不能补模型能力的底。
5. **采样偏置**：分层样本放大 gap（10.5pp vs 自然分布 5pp），必须报加权视图。
6. **答案尺度**：exe_ans 尺度混乱（小数 vs ×100 vs 单位），使"语义正确但尺度错"被计错，虚增 strategy 失败。

## 6. E. Go / No-Go 判断

### 结论：CONDITIONAL GO

**现象存在且满足进入 selector 设计的门槛**：Oracle gap 明显（分层 10.5pp / 自然 5pp），case-only(21) 与 strategy-only(9) 均非零，且 Both 简单拼接有 12 例负干扰——"何时用哪种记忆"是真实问题。**若只问"是否值得研究 adaptive Case/Strategy selection"，答案是 GO。**

但必须满足以下**前置条件**，否则研究会被 confound 淹没：

1. **先修 Strategy 质量与检索**（否则 strategy 臂的失败无法归因）：
   - 消除变体歧义：Strategy 需显式给出答案尺度约定，或把 ×100/小数合并为单一规范形式 + 输出时按 gold 尺度归一。
   - 提高检索：当前 32.9% 命中太低。可行且不过度工程的做法：以检索到的 case 为锚，取其 struct/公司对应的 strategy 候选集再排序（case 检索 63.6% 命中率可用）；或对 strategy 增加"问题类型"标签做粗过滤。
2. **公司条件化消融**：把"同公司模板迁移"与"跨公司推理迁移"分开报告，否则 Case 的增益来源不明。
3. **自然分布加权报告**：不再只报分层样本的 gap。
4. **selector 能力线**：Oracle 需按 bucket 报告，明确哪些类型 gap 可兑现、哪些（如 E）兑现不了。

### 一句话

**值得继续做 adaptive selection，但先把 Strategy 的"检索 + 变体规范"这两块 confound 修干净，再做公司条件化消融，才能得到可信的 Oracle gap 与 selection 上限。** 若修正后自然分布 oracle gap 仍在 3pp 以上且分类型互补仍成立，则推进 selector 设计；若跌到 ~0，则调整研究问题。

## 7. 实验产物清单

- 代码：`pilot/executor.py`（官方语义执行器，gold 2000/2000 自检）、`pilot/{llm,retrieval,prompts,run_arms,evaluate,failure_inspect}.py`、`pilot/config.py`、`pilot/DECISIONS.md`。
- 数据：`data/finqa/`（官方 4 split）；`pilot/output/case_memory.json`（6251 case）、`strategies.json`（44 策略）、`dev_sample.json`（143 条 + 分桶）、`arm_outputs.json`（每题 4 臂 raw + 检索记录）。
- 检索检查：`output/retrieval_check.json`（15 条抽查含人工判断）。
- 评估：`output/evaluation.json`（summary + per-question）、`output/per_question_full.json`、`output/failure_cases.txt`（case-only / strategy-only / 干扰全量明细）。
