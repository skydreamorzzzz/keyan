"""Strict FinQA program parser; official evaluator remains the execution reference."""
import re
from decimal import Decimal, InvalidOperation

OPS = {"add", "subtract", "multiply", "divide", "exp", "greater", "table_max", "table_min", "table_sum", "table_average"}
STEP = re.compile(r"^(?P<op>[a-z_]+)\((?P<a>[^,()]+), (?P<b>[^,()]+)\)$")

class ProgramError(ValueError): pass

def parse_strict(program):
    if not isinstance(program, str) or not program or program != program.strip():
        raise ProgramError("program must be a nonempty, unmodified string")
    # Arguments themselves use `, `; only a completed `), ` ends a step.
    steps = re.split(r"(?<=\)), ", program)
    if ", ".join(steps) != program:
        raise ProgramError("steps must use exact '), ' delimiter")
    parsed = []
    for index, step in enumerate(steps):
        match = STEP.fullmatch(step)
        if not match or match["op"] not in OPS:
            raise ProgramError("invalid step %d: %r" % (index, step))
        args = (match["a"], match["b"])
        for arg in args:
            if arg.startswith("#"):
                if not re.fullmatch(r"#[0-9]+", arg) or int(arg[1:]) >= index:
                    raise ProgramError("invalid reference %r at step %d" % (arg, index))
        parsed.append({"op": match["op"], "args": list(args)})
    return parsed

def execute_custom(program, table):
    """Independent strict executor for differential checks (no repair path)."""
    import math
    steps=parse_strict(program); values=[]
    def number(token):
        token=token.replace(",", "").replace("$", "").strip()
        if token.startswith("const_"): return -1.0 if token == "const_m1" else float(token[6:])
        if token.endswith("%"): return float(token[:-1]) / 100.0
        return float(token)
    def arg(token): return values[int(token[1:])] if token.startswith("#") else number(token)
    rows={str(r[0]): r[1:] for r in table}
    for step in steps:
        op,a,b=step["op"],step["args"][0],step["args"][1]
        if op.startswith("table_"):
            if a not in rows: raise ProgramError("table row not found: "+a)
            nums=[number(str(v).split("(")[0]) for v in rows[a]]
            value={"table_max":max,"table_min":min,"table_sum":sum,"table_average":lambda x:sum(x)/len(x)}[op](nums)
        else:
            x,y=arg(a),arg(b)
            value={"add":lambda:x+y,"subtract":lambda:x-y,"multiply":lambda:x*y,"divide":lambda:x/y,"exp":lambda:x**y,"greater":lambda:"yes" if x>y else "no"}[op]()
        values.append(value)
    result=values[-1]
    return result if isinstance(result,str) else round(result,5)

def answers_equal(left, right):
    if str(left).strip().lower() in {"yes", "no", "n/a"} or str(right).strip().lower() in {"yes", "no", "n/a"}:
        return str(left).strip().lower() == str(right).strip().lower()
    try:
        return abs(Decimal(str(left)) - Decimal(str(right))) <= Decimal("0.00001")
    except (InvalidOperation, ValueError):
        return str(left).strip() == str(right).strip()
