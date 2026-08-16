"""Stage 2 Baseline Alignment 配置。所有统一控制项集中于此。"""
import os

PILOT = "/home/tiantian/keyan/pilot"
OUT = os.path.join(PILOT, "stage2", "output")

DATA = "/home/tiantian/keyan/data/finqa"

# ---- 统一实验控制 ----
# 决策：统一用 dev 的固定种子 492 子集（匹配论文 n=492；论文未说明子集选择，用 seed 随机并记录）。
# 所有方法在同一子集上、同一模型、同一 temp、同一 prompt 模板（仅 context 段不同）。
SAMPLE_N = 492
SAMPLE_SEED = 20260816
BASE_MODEL = "DeepSeek-V4-flash[1m]"   # 统一 base model（替代论文的 Llama 3.1 8B / Ollama；记录差异）
TEMPERATURE = 0.0
EMBED_MODEL = "BAAI/bge-small-en-v1.5" # 替代论文 nomic-embed-text / Ollama；记录差异

RETRIEVAL_K = 12      # 论文默认 k=12
TOP_CASE = 4          # 经验记忆：Case top-k（沿用 Pilot）
TOP_STRATEGY = 3      # 经验记忆：Strategy top-k

# ---- Arms ----
# reproduction (free-form answer, paper metrics): baseline/rag/structured/mem0aug
# unified (program output, FinQA official metrics): baseline/rag/structured/struct_case/struct_strategy/struct_both
REPRO_ARMS = ["baseline", "rag", "structured", "mem0aug"]
# unified：2×3 因子设计 = grounding{full-doc, structured} × experience{none, case, strategy, both}
UNIFIED_ARMS = ["baseline", "rag", "structured",
                "struct_case", "struct_strategy", "struct_both",
                "fulldoc_case", "fulldoc_strategy", "fulldoc_both"]

# ---- context budgets ----
MAX_PRE_SENTS = 40
MAX_POST_SENTS = 40

LLM_MAX_TOKENS = 2000
LLM_CONCURRENCY = 12
LLM_MAX_RETRIES = 4

# 输出格式：reproduction 用 free-form（论文风格）；unified 用 FinQA program（嵌套表达式）
