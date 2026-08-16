"""4 臂提示词模板。决策：4 臂唯一差异是 memory 部分；report context 完全相同。"""

SYS = (
    "You are solving financial reasoning questions over annual report data (the FinQA benchmark). "
    "Given a financial report (a table plus surrounding text) and a question, you must produce the "
    "numerical reasoning PROGRAM that computes the answer.\n\n"
    "Operations: add, subtract, multiply, divide, exp, greater, table_max, table_min, table_sum, table_average.\n"
    "- Arithmetic ops take two operands, each either a number or a nested sub-expression.\n"
    "- table_max/table_min/table_sum/table_average take a TABLE ROW LABEL as first argument and the "
    "literal 'none' as second argument. They operate over the numeric cells of that row. "
    "E.g., table_average(2016, none).\n"
    "- Numbers may carry units/percent: use '22%' for twenty-two percent; use const_1000 / const_1000000 / "
    "const_100 / const_2 / const_3 as needed for thousands / millions / percent-scale / small counts.\n"
    "- Table cells may contain formatting noise, e.g. '-36 ( 36 )' means -36, '22% ( 22 % )' means 22%, "
    "'$ 1697.6' means 1697.6.\n"
    "- Use the EXACT operator names above. 'greater' is the comparison operator — do NOT write 'compare(...)' "
    "or infix 'A > B'; write greater(A, B).\n\n"
    "Output the program as a SINGLE nested expression, one line, no explanation, no code fences. "
    "Example output: divide(subtract(1697.6, 1739.5), 1739.5)"
)

def _case_block(c):
    facts = " ; ".join(c["gold_facts"][:3])
    return (f"Case {c['case_id']}:\n"
            f"  Question: {c['question']}\n"
            f"  Supporting facts: {facts}\n"
            f"  Program: {c['program_re']}\n"
            f"  Answer: {c['exe_ans']}")

def _strategy_block(s):
    return (f"Strategy: {s['name']}\n"
            f"  Semantic intent: {s['semantic_intent']}\n"
            f"  Problem pattern: {s['problem_pattern']}\n"
            f"  Operand roles: {s['operand_roles']}\n"
            f"  Procedure: {s['procedure']}\n"
            f"  Formula: {s['formula']}\n"
            f"  Program template: {s['template']}   (replace V1,V2,... with values from THIS report)\n"
            f"  Canonical output scale: {s['canonical_output_scale']}\n"
            f"  Unit convention: {s['unit_convention']}\n"
            f"  Caveats: {s['caveats']}")

def build_prompt(arm, question, context, cases=None, strategies=None):
    user = []
    user.append(f"REPORT:\n{context}\n")
    if arm in ("case", "case_all", "case_cc", "both_all", "both_cc"):
        user.append("SIMILAR SOLVED CASES (reference for how to extract values and structure the computation; "
                    "do NOT copy their numbers):\n" + "\n\n".join(_case_block(c) for c in cases))
    if arm in ("strategy", "both_all", "both_cc"):
        user.append("RELEVANT REASONING STRATEGIES (follow the one that applies; fill placeholders with values "
                    "from THIS report):\n" + "\n\n".join(_strategy_block(s) for s in strategies))
    user.append(f"QUESTION: {question}\n\nPROGRAM:")
    return [{"role": "user", "content": SYS + "\n\n" + "\n\n".join(user)}]
