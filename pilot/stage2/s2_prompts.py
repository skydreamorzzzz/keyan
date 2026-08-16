import s2config as config
"""统一 prompt 模板。决策：同一输出模式（free-form 或 program）下，所有架构共享同一模板，
仅 context 段不同（full doc / top-k facts / top-k facts + experience）。"""

# free-form 输出（reproduction metric：论文让 LLM 生成自由文本数值答案）
SYS_FREEFORM = (
    "You are a financial analyst answering a single-turn numerical reasoning question over a company's "
    "financial report. Answer with the final numeric value only (a number, optionally a percent sign). "
    "Do not include explanation."
)

# program 输出（unified reasoning metric：生成 FinQA 可执行程序）
SYS_PROGRAM = (
    "You are solving a financial reasoning question (FinQA). Given a financial report (a table plus "
    "surrounding text) and a question, produce the numerical reasoning PROGRAM that computes the answer.\n\n"
    "Operations: add, subtract, multiply, divide, exp, greater, table_max, table_min, table_sum, table_average.\n"
    "- Arithmetic ops take two operands, each either a number or a nested sub-expression.\n"
    "- table_* take a TABLE ROW LABEL (the text in the first column) as first argument and 'none' as second.\n"
    "- Numbers may carry units: use '22%' for twenty-two percent; const_1000/const_1000000/const_100/const_2/const_3 as needed.\n"
    "- Table cells may have noise: '-36 ( 36 )' means -36, '22% ( 22 % )' means 22%, '$ 1697.6' means 1697.6.\n"
    "- Use EXACT operator names; 'greater' not 'compare' or infix '>'.\n"
    "- Facts may appear as 'entity | column = value' (e.g., 'net cash | 2010 = 3547'). The PROGRAM "
    "operand is the numeric VALUE after '=' (use 3547), never the entity/column text.\n\n"
    "Output the program as a SINGLE nested expression, one line, no explanation, no code fences. "
    "Example: divide(subtract(1697.6, 1739.5), 1739.5)"
)

def _format_facts(facts):
    return "\n".join(f["fact"] for f in facts)

def _format_full_doc(pre_text, post_text, table):
    lines = ["TEXT BEFORE TABLE:"] + [f"s{i}: {t}" for i, t in enumerate(pre_text[:config.MAX_PRE_SENTS])]
    lines.append("TABLE:")
    for i, row in enumerate(table):
        lines.append(f"row{i}: " + " | ".join(str(c) for c in row))
    lines.append("TEXT AFTER TABLE:")
    lines += [f"t{i}: {t}" for i, t in enumerate(post_text[:config.MAX_POST_SENTS])]
    return "\n".join(lines)

def build_prompt(mode, question, context_text):
    """context_text 由调用方按架构拼好（full doc 或 facts 或 facts+experience）。"""
    sys_prompt = SYS_FREEFORM if mode == "freeform" else SYS_PROGRAM
    return [{"role": "user", "content": sys_prompt + "\n\nCONTEXT:\n" + context_text +
             f"\n\nQUESTION: {question}\n\n" + ("ANSWER:" if mode == "freeform" else "PROGRAM:")}]

def make_context(arm, doc, facts_bundle, case_blocks=None, strategy_blocks=None, memory_text=None):
    """按架构组装 context 文本。facts_bundle 提供 rag_facts / struct_facts（已检索 top-k）。"""
    if arm == "baseline":
        return _format_full_doc(doc["pre_text"], doc["post_text"], doc["table"])
    if arm == "rag":
        return "RELEVANT DOCUMENT FACTS:\n" + _format_facts(facts_bundle["rag_facts"])
    if arm == "structured":
        ctx = "RELEVANT STRUCTURED FACTS (entity | column = value):\n" + _format_facts(facts_bundle["struct_facts"])
        return ctx
    if arm == "mem0aug":
        ctx = _format_full_doc(doc["pre_text"], doc["post_text"], doc["table"])
        if memory_text:
            ctx += "\n\nPRIOR MEMORIES:\n" + memory_text
        return ctx
    if arm == "struct_case":
        ctx = "RELEVANT STRUCTURED FACTS (entity | column = value):\n" + _format_facts(facts_bundle["struct_facts"])
        ctx += "\n\nSIMILAR SOLVED CASES (reference, do NOT copy their numbers):\n" + "\n\n".join(case_blocks)
        return ctx
    if arm == "struct_strategy":
        ctx = "RELEVANT STRUCTURED FACTS (entity | column = value):\n" + _format_facts(facts_bundle["struct_facts"])
        ctx += "\n\nRELEVANT REASONING STRATEGIES (follow the one that applies):\n" + "\n\n".join(strategy_blocks)
        return ctx
    if arm == "struct_both":
        ctx = "RELEVANT STRUCTURED FACTS (entity | column = value):\n" + _format_facts(facts_bundle["struct_facts"])
        ctx += "\n\nSIMILAR SOLVED CASES (reference, do NOT copy their numbers):\n" + "\n\n".join(case_blocks)
        ctx += "\n\nRELEVANT REASONING STRATEGIES (follow the one that applies):\n" + "\n\n".join(strategy_blocks)
        return ctx
    # full-doc grounding + experience（对照：经验在 full-doc 上的增益）
    if arm == "fulldoc_case":
        ctx = _format_full_doc(doc["pre_text"], doc["post_text"], doc["table"])
        ctx += "\n\nSIMILAR SOLVED CASES (reference, do NOT copy their numbers):\n" + "\n\n".join(case_blocks)
        return ctx
    if arm == "fulldoc_strategy":
        ctx = _format_full_doc(doc["pre_text"], doc["post_text"], doc["table"])
        ctx += "\n\nRELEVANT REASONING STRATEGIES (follow the one that applies):\n" + "\n\n".join(strategy_blocks)
        return ctx
    if arm == "fulldoc_both":
        ctx = _format_full_doc(doc["pre_text"], doc["post_text"], doc["table"])
        ctx += "\n\nSIMILAR SOLVED CASES (reference, do NOT copy their numbers):\n" + "\n\n".join(case_blocks)
        ctx += "\n\nRELEVANT REASONING STRATEGIES (follow the one that applies):\n" + "\n\n".join(strategy_blocks)
        return ctx
    raise ValueError(arm)
