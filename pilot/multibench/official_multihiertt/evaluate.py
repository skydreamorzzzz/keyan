"""Minimal official-compatible MultiHiertt evaluator functions.

Source: https://github.com/psunlpgroup/MultiHiertt/blob/main/evaluate.py
This file vendors the scoring functions used by the official script. CLI
prediction-file merging and training-output plumbing are intentionally omitted.
"""
from __future__ import annotations

import math

from .utils.program_generation_utils import eval_program, program_tokenization
from .utils.span_selection_utils import get_span_selection_metrics
from .utils.utils import str_to_num


def evaluate_program_result(pred_prog, gold_prog):
    """Official execution accuracy for program predictions."""
    invalid_flag, exe_res = eval_program(pred_prog)
    gold = program_tokenization(gold_prog)
    invalid_flag, exe_gold_res = eval_program(gold)
    if invalid_flag:
        print(gold)
    if exe_res == exe_gold_res:
        exe_acc = 1
    else:
        exe_acc = 0
    return exe_acc, exe_acc


def evaluate_span_program_result(span_ans, prog_ans):
    """Official mixed span/program answer comparison."""
    span_ans = str(span_ans)
    if str_to_num(span_ans) != "n/a":
        span_ans = str_to_num(span_ans)
        if math.isclose(prog_ans, span_ans, abs_tol=min(abs(min(prog_ans, span_ans) / 1000), 0.1)):
            exact_match, f1 = 1, 1
        else:
            exact_match, f1 = 0, 0
    else:
        exact_match, f1 = get_span_selection_metrics(span_ans, str(prog_ans))
    return exact_match, f1
