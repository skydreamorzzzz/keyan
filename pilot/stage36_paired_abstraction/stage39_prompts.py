#!/usr/bin/env python3
"""
Stage 39: Frozen Prompt Protocol
All arms share identical system prompt, document rendering, and output instruction.
Only memory representation varies.
"""

SYSTEM_PROMPT = """You are a financial reasoning assistant. Given a document with text and a table, answer the question by generating a FinQA program.

A FinQA program is a sequence of operations with concrete operands from the document. Each operation takes arguments and returns a result that can be referenced in later steps.

Syntax:
- operation(arg1, arg2) → returns result stored as #0
- operation(#0, arg3) → uses previous result, returns #1
- Continue until final answer

Available operations: add, subtract, multiply, divide, exp, greater, table_sum, table_average, table_max, table_min

Requirements:
- Use ONLY concrete values from the current document (text or table cells)
- Output a fully executable program, not just operator names
- Reference intermediate results with #0, #1, #2, ...

Output format:
PROGRAM: operation(arg1, arg2), operation(#0, arg3), ...
ANSWER: [final numeric answer]"""


OUTPUT_INSTRUCTION = """Generate a FinQA program to answer the question above.

Remember:
- Use concrete operands from the CURRENT document
- Output a fully executable program with all arguments specified
- Do NOT output only operator names

Your response:"""


def render_document(target):
    """Render document context identically across arms."""
    pre_text = "\n".join(target['pre_text'])
    post_text = "\n".join(target['post_text'])

    table_rows = []
    for row in target['table_ori']:
        table_rows.append(" | ".join(str(cell) for cell in row))
    table_str = "\n".join(table_rows)

    return f"""Document context:
{pre_text}

Table:
{table_str}

{post_text}

Question: {target['qa']['question']}"""


def construct_prompt(target, memory_section, arm_name):
    """Assemble prompt with shared components + arm-specific memory."""

    prompt_parts = [
        SYSTEM_PROMPT,
        "",
        render_document(target),
        "",
        memory_section,
        "",
        OUTPUT_INSTRUCTION
    ]

    return "\n".join(prompt_parts)
