"""Oracle Pilot 配置：所有关键决策集中在此，方便复盘。"""
import os

# ---- 数据 ----
DATA_DIR = "/home/tiantian/keyan/data/finqa"
PILOT_DIR = "/home/tiantian/keyan/pilot"
OUT_DIR = os.path.join(PILOT_DIR, "output")

# ---- LLM ----
LLM_MODEL = os.environ.get("ANTHROPIC_MODEL", "DeepSeek-V4-flash[1m]")
LLM_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
LLM_MAX_TOKENS = 2500
LLM_TEMPERATURE = 0.0
LLM_CONCURRENCY = 12
LLM_MAX_RETRIES = 4

# ---- 采样 ----
# 决策：dev 分层抽样 150 条，配额偏向结构化/策略型类型（对互补性问题更有信息量）。
# 理由：自然分布里单步占 55%，长链/表格聚合/比较等类型样本过少，无法分析分类型互补。
# 风险：整体 accuracy 不等于自然分布；报告里同时给分 bucket 结果 + 自然分布加权参考。
DEV_SAMPLE_N = 150
DEV_SEED = 20260815
BUCKET_QUOTA = {
    "A_comparison_yesno": 12,
    "B_table_aggregation": 14,
    "C_unitscaling_multi": 18,
    "D_multistep4plus": 12,
    "E_3step": 12,
    "F_2step": 44,
    "G_1step": 38,
    "H_other": 0,
}

# ---- 检索 ----
EMBED_MODEL = "BAAI/bge-small-en-v1.5"   # 决策：英文强检索 baseline，384 维，GPU 可跑
EMBED_DEVICE = "cpu"   # GPU 驱动与 torch 2.13 不兼容（RuntimeError driver too old），改 CPU；6251 条短文本可接受
TOP_K_CASE = 4
TOP_K_STRATEGY = 3
RETRIEVAL_CHECK_N = 15     # 检索 sanity check 抽查条数

# ---- Case Memory ----
# 决策：Case 直接来自 train，不重写。每条 = 一个 train 样本。
# 检索文本 = question + problem_kind + gold_facts（渲染事实）。
CASE_INDEX_ALL = True      # 全量 6251 入索引

# ---- Strategy Memory ----
# 决策：从分层 train 样本聚类 + LLM 抽象生成小策略池；QC 后再用。
STRATEGY_TRAIN_SAMPLE_N = 120
STRATEGY_QC_N = 24         # 抽样质检条数

# ---- 评估 ----
EXE_TOL = 1e-4             # 执行结果容差（绝对值或相对）
