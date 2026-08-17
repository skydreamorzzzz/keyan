"""Subset of official MultiHiertt program evaluation utilities.

Source: https://github.com/psunlpgroup/MultiHiertt/blob/main/utils/program_generation_utils.py
Only program tokenization and execution are vendored for evaluator use.
"""
from __future__ import annotations

from .utils import str_to_num

all_ops = ["add", "subtract", "multiply", "divide", "exp"]


def program_tokenization(original_program):
    original_program = str(original_program).split(",")
    program = []
    for tok in original_program:
        tok = tok.strip()
        cur_tok = ""
        for c in tok:
            if c == ")":
                if cur_tok != "":
                    program.append(cur_tok)
                    cur_tok = ""
            cur_tok += c
            if c in ["(", ")"]:
                program.append(cur_tok)
                cur_tok = ""
        if cur_tok != "":
            program.append(cur_tok)
    program.append("EOF")
    return program


def eval_program(program):
    invalid_flag = 0
    this_res = "n/a"
    try:
        program = list(program)[:-1]
        for ind, token in enumerate(program):
            if ind % 4 == 0:
                if token.strip("(") not in all_ops:
                    return 1, "n/a"
            if (ind + 1) % 4 == 0:
                if token != ")":
                    return 1, "n/a"
        program = "|".join(program)
        steps = program.split(")")[:-1]
        res_dict = {}
        for ind, step in enumerate(steps):
            step = step.strip()
            if len(step.split("(")) > 2:
                invalid_flag = 1
                break
            op = step.split("(")[0].strip("|").strip()
            args = step.split("(")[1].strip("|").strip()
            arg1 = args.split("|")[0].strip()
            arg2 = args.split("|")[1].strip()
            if "#" in arg1:
                arg1 = res_dict[int(arg1.replace("#", ""))]
            else:
                arg1 = str_to_num(arg1)
                if arg1 == "n/a":
                    invalid_flag = 1
                    break
            if "#" in arg2:
                arg2 = res_dict[int(arg2.replace("#", ""))]
            else:
                arg2 = str_to_num(arg2)
                if arg2 == "n/a":
                    invalid_flag = 1
                    break
            if op == "add":
                this_res = arg1 + arg2
            elif op == "subtract":
                this_res = arg1 - arg2
            elif op == "multiply":
                this_res = arg1 * arg2
            elif op == "divide":
                this_res = arg1 / arg2
            elif op == "exp":
                this_res = arg1 ** arg2
            res_dict[ind] = this_res
        if this_res != "n/a":
            this_res = round(this_res, 5)
    except Exception:  # noqa: BLE001 - official code catches all exceptions.
        invalid_flag = 1
    return invalid_flag, this_res
