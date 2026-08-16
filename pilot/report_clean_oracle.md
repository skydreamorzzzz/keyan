# Clean Oracle 报告：清洗后的 Case / Strategy 互补性与最终 Go/No-Go

日期 2026-08-16。承接 Stage-2 Oracle Pilot（`report_pilot.md`）。本报告回答 Q1–Q5，并给出 Stage 1 的最终 Go/No-Go。
实验资产：`pilot/`（代码）、`pilot/output/`（产物）、`pilot/DECISIONS.md`（决策日志，已更新）。

## 0. 相对 Stage-2 做了什么（清洗步骤）

| 项 | Stage-2 | Clean Oracle |
|---|---|---|
| Strategy 池 | 44 条（变体/尺度不统一） | **28 条规范策略**（合并 %change 三种变体→小数规范；合并求和/平均各形；补复利；删除低置信 S020） |
| Strategy 尺度 | fraction 与 ×100 混用 | **规范为 fraction**（train 统计：percent-change 族 95.2% 用小数；全量 ×100 仅 4.1%） |
| Strategy 单位 | 混乱 | 明确：const 因子由表头单位决定（thousands→const_1000, millions→const_1000000），平均除数=值个数 |
| Strategy 检索 | 纯 embedding，family-hit@3=32.9% | **case-anchored 候选过滤**（用 top-8 cases 的 struct 缩小候选再 embedding 排序），family-hit@3=**64.3%(strat)/76.0%(nat)** |
| Case 消融 | 无 | **Case-All vs Case-CrossCompany** |
| 样本 | 143 分层 | 143 分层 + **250 自然分布**（固定种子，与分层重叠 36 条=14.4%） |
| Arms | 4 | **6**：no / case_all / case_cc / strategy / both_all / both_cc |

**清洗依据全部来自 train 统计，非 dev**（见 `clean_strategies.py` 头部注释）。

> 工程注：修复了两个 pipeline bug（run_arms 的 `xcomp` 变量泄漏导致所有 case 臂误排同公司；prompts 漏判 `case_all` 导致该臂无案例）。最终数据已复核：case_all 与 Stage-2 case 输出 132/143 一致（其余 11 条为模型 temp-0 下的非确定性，非 bug）。

## 1. 主结果（execution accuracy）

### 1.1 四臂 + CrossCompany + Oracle

| 指标 | no | case_all | case_cc | strategy | both_all | both_cc |
|---|---|---|---|---|---|---|
| **strat (n=143)** | 0.5315 | **0.6294** | 0.5804 | 0.6154 | 0.6224 | 0.5944 |
| **nat (n=250)** | 0.556 | 0.676 | 0.656 | 0.660 | **0.696** | 0.684 |

- **strat**：Best Fixed = case_all (0.6294)；Oracle = 0.7343；**Gap = 0.1049**
- **nat**：Best Fixed = both_all (0.696)；Oracle = 0.784；**Gap = 0.088**

### 1.2 Contingency（case_all vs strategy）

| | strat | nat |
|---|---|---|
| both 对 | 79 | 147 |
| **case-only** | **11** | **22** |
| **strategy-only** | **9** | **18** |
| neither | 44 | 63 |

### 1.3 naive Both 干扰

| | strat | nat |
|---|---|---|
| both 错但单臂对 | 10 | 17 |
| both 对但两单臂错 | 0 | 4 |

→ strat 上 both_all (0.6224) < case_all (0.6294)；nat 上 both_all 是最佳 fixed (0.696) 但仍低于 oracle (0.784)。**naïve 拼接达不到 oracle，负干扰仍在**。

### 1.4 Retrieval-conditioned

| 条件 | strat no | strat strategy | nat no | nat strategy |
|---|---|---|---|---|
| strategy family 命中 | 0.576 | **0.761** | 0.595 | **0.763** |
| strategy family 未命中 | 0.451 | **0.353** | 0.433 | **0.333** |
| case same-struct 命中 | 0.615 | — | 0.601 | — |
| case same-struct 未命中 | 0.385 | — | 0.444 | — |

### 1.5 Cross-Company（Q3）

| | strat | nat |
|---|---|---|
| case_all − case_cc | +4.9pp | +2.0pp |
| case_cc − no | **+4.9pp** | **+10.0pp** |
| top-4 含同公司均值 | 1.83/4 | 1.60/4 |
| case_all_win / case_cc_win | 12 / 5 | 12 / 7 |

### 1.6 分 bucket（exec acc，strat）

| bucket | n | no | case_all | case_cc | strategy | both_all | oracle |
|---|---|---|---|---|---|---|---|
| A comparison | 10 | **1.00** | 0.70 | 0.70 | 0.90 | 0.70 | 1.00 |
| B table_agg | 14 | **1.00** | 1.00 | 0.857 | 0.929 | 1.00 | 1.00 |
| C unitscaling | 18 | 0.167 | 0.278 | 0.167 | 0.278 | **0.333** | 0.556 |
| D multistep | 7 | 0.143 | 0.286 | 0.429 | **0.571** | 0.429 | 0.714 |
| E 3step | 12 | 0.083 | 0.167 | 0.083 | 0.083 | 0.083 | 0.167 |
| F 2step | 44 | 0.682 | **0.750** | 0.727 | 0.727 | 0.750 | 0.795 |
| G 1step | 38 | 0.447 | **0.711** | 0.658 | 0.632 | 0.658 | 0.763 |

## 2. Q1：更干净的设定下 Case / Strategy 仍互补吗？

**是。** 两个方向都稳定存在：
- strat：case-only 11 + strategy-only 9；nat：case-only 22 + strategy-only 18（占 16%）。
- 分 bucket 互补方向与 Stage-2 一致：**Case 主导常见模板型（G/F 单双步、占比、单价、行标签精确匹配）；Strategy 主导结构化/长链/跨年聚合/平均（D multistep、C unitscaling、B 中的平均）**。
- 机制（来自 failure cases）：Case 靠近同构模板模仿（AAPL/2008 同公司案例给出正确行标签；ETFC/UPS 同公司累计收益案例给出精确 `subtract(divide(subtract(...),const_100),...)` 形状）；Strategy 靠抽象骨架消歧（AES/2015、JPM/2018 的 C06 平均=sum÷count 而非错误行标签；TSCO/2017、LKQ/2016 的 C18 累计收益差）。

## 3. Q2：自然分布 Oracle Gap 是否仍存在？

**是，且稳定。** nat gap = **8.8pp**（strat 10.5pp），与 Stage-2 的 5pp（加权估计）和 10.5pp（分层）一致或更高。远超 ≥3pp 参考门槛。gap 集中在 C（unitscaling，oracle−best ≈ 22pp）、D、F、G、A；**E 3step 是模型能力地板（oracle 0.167），memory 无法兑现**。

## 4. Q3：Cross-company 后 Case 优势还剩多少？

**仍实质存在。** case_cc 相对 no-memory：strat +4.9pp、nat +10.0pp。同公司贡献额外 +2~5pp（case_all−case_cc），方向性上 case_all_win(12) > case_cc_win(5/7)。**结论：Case 收益不是主要来自同公司模板复用——跨公司普遍经验迁移真实存在；同公司是叠加的增强，而非全部来源。**（当 top-4 无同公司案例时，case_all 仍 0.588(strat)/0.577(nat)，远高于 no 的 0.385/0.444。）

## 5. Q4：Strategy-only 独占正确是否稳定，而非检索 bug 偶然？

**稳定存在，但有两点限定。**
- 在检索改善后（family-hit 64–76%），strat 仍有 9 / nat 18 个 strategy-only 独占正确，非检索 bug 偶然。
- **限定 1**：其中一部分是"case 误导而 strategy 不误导"（如 UNP/2011、PNC/2009 比较题：case 臂过度推导 `divide(greater(...),1)`，strategy 臂即使检索到的是错误族也靠自身推理答对）。所以 strategy-only 部分是"strategy 直接给对"+"strategy 中性无害"的混合。
- **限定 2**：strategy 价值仍强依赖检索——family 命中时 +18pp，未命中时反噬 −10~12pp。这是 selector 设计必须处理的。

## 6. Q5：naïve Both 负干扰仍存在？

**是。** strat 10 例、nat 17 例 both 错但单臂对；strat 上 both_all 低于 case_all。但 nat 上 both_all 已是最佳 fixed。**naïve 拼接不能兑现 oracle gap，selector 是必要机制。**

## 7. 最终 Go / No-Go：**GO**

对照参考标准逐条核验：

| 标准 | 结果 |
|---|---|
| 自然分布 Oracle Gap ≥3pp | **8.8pp ✓**（分层 10.5pp） |
| Case-only / Strategy-only 稳定存在 | **22/18（nat）、11/9（strat）✓** |
| 不能完全被同公司泄漏解释 | ✓（cross-company Case 仍 +10pp） |
| 不能完全被 retrieval failure 解释 | ✓（strategy-only 在 family-hit 76% 下仍稳定） |

**判断：GO — 进入下一阶段 Adaptive Memory Selector 设计。**

### 推进建议（selector 设计必须吸收的教训）
1. **selector 的候选空间应含 None（无记忆）**：A/B 桶简单题 memory 反而有害（no=1.0 > 各 memory 臂），Oracle 包含 no 臂。
2. **检索质量是 selector 的地基**：strategy 依赖 case-anchored 检索（family-hit 76%）；selector 不应绕过检索做纯文本匹配。
3. **scale 规范化进 prompt**：%change 统一小数输出，可在 selector 的 prompt 层沿用 C02 规范。
4. **E 3step 是能力地板**：selector 对这类题目没有兑现空间，不必为此分配复杂度。
5. **同公司是 feature 不是 bug**：selector 可显式利用"同公司案例"作为强信号，但要记录以便消融归因。

### 残余 confound（如实记录，不掩盖）
- Strategy 检索未命中时反噬（-10~12pp）——selector 需要能识别"检索不靠谱"。
- 模型 temp-0 非完全确定（143 中 11 条 case 输出与上轮不一致）——结果有 ~5% 波动。
- 分层/自然两视图 gap 分别为 10.5/8.8pp，用哪个作目标需在研究设计里定死（建议自然分布为主）。

## 8. 工程产物清单（本次新增）

- `pilot/clean_strategies.py` + `output/strategies_clean.json`（28 条规范策略）+ `output/strategy_clean_diff.json`（清洗前后映射日志）
- `pilot/measure_retrieval.py`（检索命中率测量：baseline vs case-anchored）
- `pilot/build_natural_sample.py` + `output/dev_sample_natural.json`（250 条，种子 20260817，与分层重叠 36）
- `pilot/run_arms.py`（6 臂，双样本，case-anchored 检索，cache 恢复）+ `output/arm_outputs_clean.json`
- `pilot/evaluate_clean.py` + `output/evaluation_clean.json` + `output/per_question_clean_full.json`
- `pilot/failure_inspect_clean.py` + `output/failure_cases_clean.txt`（case_only / strategy_only / 干扰 / xcomp 差异全量明细）
- `pilot/DECISIONS.md`（已更新：清洗、检索、xcomp、双样本、两处 bug 修复记录）
