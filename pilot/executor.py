"""FinQA program 执行器：官方 evaluate.py 语义移植 + program_re 解析/linear 化。

参考 official_code/evaluate.py 的 str_to_num / eval_program / equal_program / program_tokenization。
目标：gold program_re 执行结果 == gold exe_ans（自检 100%）。
"""
import re

ALL_OPS = ["add", "subtract", "multiply", "divide", "exp", "greater",
           "table_max", "table_min", "table_sum", "table_average"]

# ---------------- str_to_num（官方语义） ----------------
def str_to_num(text):
    text = str(text).replace(",", "")
    try:
        return float(text)
    except ValueError:
        if "%" in text:
            text = text.replace("%", "")
            try:
                return float(text) / 100.0
            except ValueError:
                return "n/a"
        elif "const" in text:
            text = text.replace("const_", "")
            if text == "m1":
                text = "-1"
            try:
                return float(text)
            except ValueError:
                return "n/a"
        else:
            return "n/a"

def process_row(row_in):
    row_out = []
    for num in row_in:
        num = str(num).replace("$", "").strip()
        num = num.split("(")[0].strip()
        num = str_to_num(num)
        if num == "n/a":
            return "n/a"
        row_out.append(num)
    return row_out

# ---------------- program_re 解析（嵌套表达式 -> AST) ----------------
_TOKEN = re.compile(r'[(),]')

def tokenize_re(pr):
    # split nested program string into tokens: op( , numbers , const_ , % , nested
    toks = []
    for part in _TOKEN.split(pr):
        part = part.strip()
        if part:
            toks.append(part)
    return toks

def parse_program_re(pr):
    """program_re -> linear steps list[(op, arg1, arg2)]。
    行标签可含空格（如 table_max(interest rate hedges, none)）。
    arg 可为字面量（数字/const_/%/行标签）或 '#'+step_index。"""
    s = pr.strip()
    pos = [0]

    def match(ch):
        if pos[0] < len(s) and s[pos[0]] == ch:
            pos[0] += 1
            return True
        return False

    def parse_expr():
        # op name then '('
        start = pos[0]
        while pos[0] < len(s) and (s[pos[0]].isalpha() or s[pos[0]] == '_'):
            pos[0] += 1
        op = s[start:pos[0]]
        if not match('('):
            raise ValueError(f"expected '(' after op in {s[start:pos[0]+10]!r}")
        arg1 = parse_arg()
        match(',')
        arg2 = parse_arg()
        if not match(')'):
            raise ValueError(f"expected ')' closing {op} in {s!r}")
        return (op, arg1, arg2)

    def parse_arg():
        # skip spaces
        while pos[0] < len(s) and s[pos[0]] == ' ':
            pos[0] += 1
        # nested function call? look ahead for `opname(`
        m = re.match(r'[a-z_]+\(', s[pos[0]:])
        if m:
            return parse_expr()
        # literal: read until a top-level ',' or ')' (no nesting here)
        start = pos[0]
        while pos[0] < len(s) and s[pos[0]] not in ",)":
            pos[0] += 1
        tok = s[start:pos[0]].strip()
        return tok

    ast = parse_expr()
    # post-order linearize
    steps = []
    def emit(node):
        op, a1, a2 = node
        def to_arg(a):
            if isinstance(a, tuple):
                return '#' + str(emit(a))
            return a
        x1 = to_arg(a1)
        x2 = to_arg(a2)
        steps.append((op, x1, x2))
        return len(steps) - 1
    emit(ast)
    return steps

# ---------------- 官方 linear 解析 ----------------
def program_tokenization(original_program):
    original_program = original_program.split(', ')
    program = []
    for tok in original_program:
        cur = ''
        for c in tok:
            if c == ')':
                if cur:
                    program.append(cur); cur = ''
            cur += c
            if c in '()':
                program.append(cur); cur = ''
        if cur:
            program.append(cur)
    program.append('EOF')
    return program

def parse_linear_steps(prog_str):
    """线性 program 字符串 -> steps list[(op,arg1,arg2)]"""
    toks = program_tokenization(prog_str)[:-1]  # drop EOF
    steps = []
    i = 0
    while i + 3 < len(toks):
        op = toks[i].strip('(')
        if op not in ALL_OPS:
            raise ValueError(f"unknown op {op!r} in {prog_str!r}")
        steps.append((op, toks[i+1], toks[i+2]))
        i += 4
    return steps

# ---------------- 执行 ----------------
def exec_steps(steps, table):
    """执行 linear steps，返回 (ok, result)。ok=False 表示 invalid。"""
    table_dict = {row[0]: row[1:] for row in table}
    res_dict = {}
    for ind, (op, a1, a2) in enumerate(steps):
        if op in ("add", "subtract", "multiply", "divide", "exp", "greater"):
            if a1.startswith('#'):
                v1 = res_dict.get(int(a1[1:]))
            else:
                v1 = str_to_num(a1)
            if a2.startswith('#'):
                v2 = res_dict.get(int(a2[1:]))
            else:
                v2 = str_to_num(a2)
            if v1 in (None, 'n/a') or v2 in (None, 'n/a'):
                return False, "n/a"
            if op != "greater" and (not isinstance(v1, (int, float)) or not isinstance(v2, (int, float))):
                return False, "n/a"
            try:
                if op == "add": r = v1 + v2
                elif op == "subtract": r = v1 - v2
                elif op == "multiply": r = v1 * v2
                elif op == "divide":
                    if v2 == 0: return False, "n/a"
                    r = v1 / v2
                elif op == "exp":
                    if v1 < 0 and v2 != int(v2): return False, "n/a"
                    r = v1 ** v2
                elif op == "greater": r = "yes" if v1 > v2 else "no"
            except Exception:
                return False, "n/a"
            res_dict[ind] = r
        elif "table" in op:
            # 与官方一致：table op 第一个参数必须是表行标签；'#' 引用视为 invalid
            if a1.startswith('#'):
                return False, "n/a"
            if a1 not in table_dict:
                return False, "n/a"
            num_row = process_row(table_dict[a1])
            if num_row == "n/a":
                return False, "n/a"
            if op == "table_max": r = max(num_row)
            elif op == "table_min": r = min(num_row)
            elif op == "table_sum": r = sum(num_row)
            elif op == "table_average": r = sum(num_row)/len(num_row)
            else:
                return False, "n/a"
            res_dict[ind] = r
        else:
            return False, "n/a"
    final = res_dict.get(len(steps)-1)
    if final is None:
        return False, "n/a"
    return True, final

def normalize_program(raw):
    """把模型的输出规范化成可解析的嵌套表达式。
    - 去掉 code fences / 包裹文本
    - compare( -> greater(
    - 顶层 infix 'A > B' -> greater(A, B)
    - 若含 "#N" 引用则是 linear 形式，返回 'LINEAR:' 前缀交给 linear 解析器
    """
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[-1] if "\n" in raw else raw
    # extract first parenthesized op expression if there's extra prose
    m = re.search(r'([a-z_]+\(.*)$', raw, re.S)
    if m:
        raw = m.group(1).strip()
    raw = raw.replace("compare(", "greater(")
    if "#" in raw:
        return "LINEAR:" + raw
    # top-level infix > handling: split at '>' outside parentheses
    if ">" in raw:
        depth = 0; idx = -1
        for i, ch in enumerate(raw):
            if ch == '(': depth += 1
            elif ch == ')': depth -= 1
            elif ch == '>' and depth == 0:
                idx = i; break
        if idx > 0:
            raw = f"greater({raw[:idx].strip()}, {raw[idx+1:].strip()})"
    return raw

def exec_program_re(pr, table):
    pr = normalize_program(pr)
    if pr.startswith("LINEAR:"):
        return exec_linear_str(pr[len("LINEAR:"):], table)
    try:
        steps = parse_program_re(pr)
    except Exception:
        return False, "parse_error"
    return exec_steps(steps, table)

def exec_linear_str(prog_str, table):
    try:
        steps = parse_linear_steps(prog_str)
    except Exception:
        return False, "parse_error"
    return exec_steps(steps, table)

# ---------------- 结果匹配 ----------------
def match_result(pred, gold):
    """执行结果是否与 gold exe_ans 一致。gold 可为数值或 yes/no。"""
    if pred == "parse_error" or pred == "n/a":
        return False
    if isinstance(gold, str):
        return pred == gold
    gold = float(gold)
    if not isinstance(pred, (int, float)):
        return False
    return abs(float(pred) - gold) <= max(1e-4, 1e-4 * abs(gold))

# ---------------- 结构匹配（模板层） ----------------
def canonical_re(pr):
    """program_re -> 符号化模板字符串：数字->NUM, const->CONST, 百分比->PCT, 表行标签->ROW:<label>。
    用于「程序结构是否与 gold 同模板」的近似比较（非官方 equal_program）。"""
    s = pr.strip()
    # simple recursive canonicalization via parse tree
    try:
        steps = parse_program_re(s)
        return "|".join(f"{op}({canon_arg(a)},{canon_arg(b)})" for op, a, b in steps)
    except Exception:
        return None

def canon_arg(a):
    if a.startswith('#'):
        return '#' + a[1:]
    if a == "none":
        return "none"
    if "%" in a:
        return "PCT"
    if "const" in a:
        return "CONST"
    try:
        float(a)
        return "NUM"
    except ValueError:
        return "ROW:" + a

# ---------------- self-test ----------------
if __name__ == "__main__":
    import json
    train = json.load(open('/home/tiantian/keyan/data/finqa/train.json'))
    import random
    rng = random.Random(0)
    ok = 0; fail = []
    for x in rng.sample(train, 300):
        pr = x['qa']['program_re']
        gold = x['qa']['exe_ans']
        okp, res = exec_program_re(pr, x['table'])
        if okp and match_result(res, gold):
            ok += 1
        else:
            fail.append((x['id'], pr, gold, res))
    print(f"exec gold program_re: {ok}/300")
    for f in fail[:8]:
        print("  FAIL:", f)
    # linear parse + exec self-test
    ok2 = 0
    for x in rng.sample(train, 300):
        gold = x['qa']['exe_ans']
        okp, res = exec_linear_str(x['qa']['program'], x['table'])
        if okp and match_result(res, gold):
            ok2 += 1
    print(f"exec gold linear program: {ok2}/300")
