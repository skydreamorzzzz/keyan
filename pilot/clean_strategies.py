"""清洗 Strategy 池：规范、无歧义、可复用。

依据（全部来自 train 统计，非 dev）：
- percent-change 族（subtract,divide）答案尺度：fraction 1263 / ×100 64 → 规范尺度 = fraction。
- 全部程序含 const_100 作输出尺度仅 256/6251（4.1%）→ 默认不用 ×100。
- avg-of-3（add,add,divide）除数：const_3 76 / const_2 8 → const_n = 值个数。
- per-unit 族单位因子：const_1000 与 const_1000000 各半 → 因子由表头单位决定（通用规则）。
- 同 struct 多语义（divide 单步：1881 ratio/percent/portion，247 其他）→ 用问题模式区分，不放同一策略里混淆。

合并/删除理由：
- S002/S019/S022（percent change 三种程序形式）→ 合并为 C02（规范 fraction；等价形 new/old-1 注明）。
- S005/S011/S024/S034（求和各形）→ C04（显式值求和）与 C05（表行求和）区分。
- S007/S016/S025（平均）→ C06（显式值平均）与 C07（表行平均）区分。
- S001/S006/S028/S031（ratio/占比）→ C01（规范 fraction）。
- S020（reverse_engineering，低置信）→ 删除。
- S037（interval，实为 difference）→ 并入 C03。
- S041（... 模板）→ 并入 C04。
- S035（带符号求和）、S017（部分/总计）→ 并入 C01/C04 的 caveat。
"""
import json, os, random, collections, re
import config
import finqa_common as fc

CANONICAL = [
    dict(
        name="ratio_part_to_whole", semantic_intent="求某部分占整体的比例/百分比/占比",
        problem_pattern="question asks what percent/portion/ratio/fraction/share of a whole a component represents",
        operand_roles="V_part=component value; V_whole=total/base value (same period & category)",
        procedure="1) identify component and whole from the report; 2) convert units so both match; 3) divide part by whole",
        formula="result = part / whole",
        template="divide(V_part, V_whole)",
        canonical_output_scale="fraction (0-1); FinQA gold 95%+ uses fraction even when question says percent; do NOT multiply by 100 unless the answer value must be an integer percent",
        unit_convention="part and whole must share units; if table header says thousands/millions, convert with const_1000/const_1000000 on either operand first",
        program_family=[["divide"], ["divide", "multiply"], ["multiply", "divide"]],
        caveats="ensure part is a subset of whole; mind 'in thousands/millions' headers; negative values in parentheses mean the signed number",
    ),
    dict(
        name="percentage_change", semantic_intent="两值之间的百分比变化/增长率",
        problem_pattern="question asks percent change/increase/decrease/growth between two values, or by what % value changed from year A to year B",
        operand_roles="V_new=later/current value; V_old=earlier/base value",
        procedure="1) subtract old from new; 2) divide by old",
        formula="result = (new - old) / old",
        template="divide(subtract(V_new, V_old), V_old)",
        canonical_output_scale="fraction (e.g. 0.05 for +5%); train 95% of this family uses fraction; equivalent form new/old - 1 is acceptable; do NOT multiply by 100 (only ~5% of gold do)",
        unit_convention="new and old in same units",
        program_family=[["subtract", "divide"], ["divide", "subtract"], ["subtract", "subtract", "divide"]],
        caveats="order matters: new minus old; denominator is old; negative result = decrease",
    ),
    dict(
        name="absolute_difference", semantic_intent="两值之差/净变化",
        problem_pattern="question asks net change/difference or how much more/less between two values (often across years)",
        operand_roles="V_later=value to subtract from; V_earlier=value subtracted",
        procedure="1) identify the two values; 2) subtract earlier from later per question direction",
        formula="result = later - earlier",
        template="subtract(V_later, V_earlier)",
        canonical_output_scale="same units as inputs; may be negative",
        unit_convention="inputs in same unit",
        program_family=[["subtract"], ["subtract", "subtract"]],
        caveats="'from A to B' means B - A; negative-number formatting '-36 ( 36 )' means -36",
    ),
    dict(
        name="total_sum_values", semantic_intent="若干显式给出的数值求和",
        problem_pattern="question asks the total/combined amount of N explicitly listed values (e.g. annual maturities in years 1..5)",
        operand_roles="V1..Vn = the values to sum (n = how many appear)",
        procedure="1) enumerate all values the question covers; 2) add them in a left-nested chain",
        formula="result = V1 + V2 + ... + Vn",
        template="add(V1, add(V2, add(V3, V4)))",
        canonical_output_scale="same units as inputs",
        unit_convention="all values same unit",
        program_family=[["add"], ["add", "add"], ["add", "add", "add"], ["add", "add", "add", "add"]],
        caveats="left-nest the adds; do not use table_sum unless the values form a single table row",
    ),
    dict(
        name="total_sum_table_row", semantic_intent="对表某行跨列求和（如 N 年合计）",
        problem_pattern="question asks the total/sum of a line item over multiple periods, and the line item is a table row",
        operand_roles="V_row_label = exact label of the table row (first column)",
        procedure="1) locate the row; 2) apply table_sum over its numeric cells",
        formula="result = sum of row cells",
        template="table_sum(V_row_label, none)",
        canonical_output_scale="same units as row cells (read header for thousands/millions)",
        unit_convention="row units given by header",
        program_family=[["table_sum"]],
        caveats="row label must match the first-column text exactly; cells like '-95.9 ( 95.9 )' are -95.9",
    ),
    dict(
        name="average_n_values", semantic_intent="若干显式数值的平均",
        problem_pattern="question asks the average/mean of N values each stated explicitly (e.g. capital expenditures for 3 years)",
        operand_roles="V1..Vn = values; const_n = count of values",
        procedure="1) sum all values; 2) divide by the count",
        formula="result = (V1 + ... + Vn) / n",
        template="divide(add(V1, add(V2, V3)), const_n)",
        canonical_output_scale="same units as inputs",
        unit_convention="const_n = number of values (const_3 for 3 values, const_2 for 2, etc.)",
        program_family=[["add", "add", "divide"], ["add", "divide"], ["add", "add", "add", "divide"]],
        caveats="use count of values, not years if some years absent; don't use table_average when values are spread across rows/text",
    ),
    dict(
        name="average_table_row", semantic_intent="表某行跨列平均",
        problem_pattern="question asks average of a line item over periods and the line item is a single table row",
        operand_roles="V_row_label = exact row label",
        procedure="1) locate row; 2) table_average over its numeric cells",
        formula="result = average of row cells",
        template="table_average(V_row_label, none)",
        canonical_output_scale="same units as row cells",
        unit_convention="percent cells are averaged as decimals (22% -> 0.22)",
        program_family=[["table_average"]],
        caveats="row label must match exactly; a row with a percent column yields fraction average",
    ),
    dict(
        name="table_maximum", semantic_intent="表某行跨列最大值",
        problem_pattern="question asks largest/highest/greatest value of a line item over periods",
        operand_roles="V_row_label = exact row label",
        procedure="1) locate the row by its first-column label; 2) apply table_max over its numeric cells",
        formula="result = max of row cells",
        template="table_max(V_row_label, none)",
        canonical_output_scale="same units as row cells",
        unit_convention="row units by header",
        program_family=[["table_max"]],
        caveats="row label exact match",
    ),
    dict(
        name="table_minimum", semantic_intent="表某行跨列最小值",
        problem_pattern="question asks lowest/smallest/minimum value of a line item",
        operand_roles="V_row_label = exact row label",
        procedure="1) locate the row by its first-column label; 2) apply table_min over its numeric cells",
        formula="result = min of row cells",
        template="table_min(V_row_label, none)",
        canonical_output_scale="same units as row cells",
        unit_convention="row units by header",
        program_family=[["table_min"]],
        caveats="row label exact match",
    ),
    dict(
        name="direct_comparison", semantic_intent="判断 A 是否大于 B（yes/no）",
        problem_pattern="question is yes/no: is/are/was/did ... greater/more/less than/exceed ...",
        operand_roles="V1, V2 = the two values being compared (may be sub-expressions)",
        procedure="1) compute both sides if needed; 2) compare with greater",
        formula="result = yes if V1 > V2 else no",
        template="greater(V1, V2)",
        canonical_output_scale="'yes' or 'no'",
        unit_convention="both sides same unit",
        program_family=[["greater"], ["subtract", "greater"], ["subtract", "subtract", "greater"]],
        caveats="gold often compares two values DIRECTLY even when question sounds like 'difference in returns' — do not over-derive into ratio/difference unless the question explicitly asks for a difference",
    ),
    dict(
        name="compound_interest", semantic_intent="复利到期值/未来值",
        problem_pattern="question asks matured/future value of a bond/note/investment given principal, annual rate, and periods to maturity",
        operand_roles="V_principal=face value; V_rate=annual interest rate; V_periods=years to maturity",
        procedure="1) build (1 + rate); 2) raise to periods; 3) multiply by principal",
        formula="result = principal * (1 + rate)^periods",
        template="multiply(V_principal, exp(add(const_1, V_rate), V_periods))",
        canonical_output_scale="same units as principal",
        unit_convention="rate as % (2.0% -> 0.02); const_1 = 1; periods = maturity year - issue year",
        program_family=[["multiply", "exp", "add"], ["multiply", "exp"]],
        caveats="official answer may round intermediates; if question says 'in millions' the principal already is",
    ),
    dict(
        name="annual_amortization", semantic_intent="年摊销/年均费用 = 总额 ÷ 年数（含单位换算）",
        problem_pattern="question asks expected annual amortization expense / average yearly cost over a period",
        operand_roles="V_total=total amount; V_years=number of years; const_unit=conversion factor from header unit to base",
        procedure="1) convert total to base units (header unit); 2) divide by years",
        formula="result = (total * unit_factor) / years",
        template="divide(multiply(V_total, const_unit), V_years)",
        canonical_output_scale="base units per year",
        unit_convention="const_unit = const_1000 if header 'in thousands', const_1000000 if 'in millions', else no const",
        program_family=[["divide", "multiply"], ["multiply", "divide"], ["divide"]],
        caveats="distinguish per-year amortization (÷ years) from per-unit cost (÷ quantity)",
    ),
    dict(
        name="per_unit_cost", semantic_intent="每单位成本/每股价格 = 总额 ÷ 数量（含单位换算）",
        problem_pattern="question asks cost per unit / average price per share given a total amount and a quantity",
        operand_roles="V_total=total monetary amount; V_quantity=number of units; const_unit=conversion factor",
        procedure="1) convert total to base units; 2) divide by quantity",
        formula="result = (total * unit_factor) / quantity",
        template="divide(multiply(V_total, const_unit), V_quantity)",
        canonical_output_scale="base units per unit",
        unit_convention="const_unit from header ('in thousands'->const_1000, 'in millions'->const_1000000)",
        program_family=[["divide", "multiply"], ["multiply", "divide"]],
        caveats="quantity unit must align with total unit; 'per share' uses same rule",
    ),
    dict(
        name="price_times_quantity", semantic_intent="总值 = 单价 × 数量",
        problem_pattern="question asks the value/cost of N units at a given per-unit price",
        operand_roles="V_price=price per unit; V_quantity=number of units",
        procedure="multiply price by quantity",
        formula="result = price * quantity",
        template="multiply(V_price, V_quantity)",
        canonical_output_scale="price unit × quantity (may be millions/thousands by header)",
        unit_convention="percent price (e.g. dividend yield) is used as decimal",
        program_family=[["multiply"], ["multiply", "multiply"]],
        caveats="price and quantity same period/category",
    ),
    dict(
        name="subset_of_total_by_percentage", semantic_intent="总量的某百分比对应金额",
        problem_pattern="question asks what amount is X% of a total",
        operand_roles="V_total=base amount; V_percent=percentage (as % or decimal)",
        procedure="multiply total by percentage",
        formula="result = total * percent",
        template="multiply(V_total, V_percent)",
        canonical_output_scale="same units as total",
        unit_convention="V_percent may be written '93%' or 0.93",
        program_family=[["multiply"]],
        caveats="ensure percent applies to the right base",
    ),
    dict(
        name="proportion_of_change", semantic_intent="总变化量中某分量的占比",
        problem_pattern="question asks what portion/percentage of a total change is due to a specific component",
        operand_roles="V_component=component's change; V_new_total, V_old_total = total at two points",
        procedure="1) total change = new_total - old_total; 2) divide component's change by it",
        formula="result = component_change / (new_total - old_total)",
        template="divide(V_component, subtract(V_new_total, V_old_total))",
        canonical_output_scale="fraction",
        unit_convention="component and totals same unit",
        program_family=[["divide", "subtract"], ["divide", "subtract", "subtract"]],
        caveats="numerator is the component's CHANGE, not its total value",
    ),
    dict(
        name="ratio_of_aggregates", semantic_intent="两个聚合量的比值",
        problem_pattern="question asks ratio of one aggregate to a sum of components",
        operand_roles="V_numerator=aggregate; V1..Vn = denominator components",
        procedure="1) sum denominator components; 2) divide",
        formula="result = numerator / (sum of components)",
        template="divide(V_numerator, add(V1, V2))",
        canonical_output_scale="fraction (can exceed 1)",
        unit_convention="numerator and denominator same unit",
        program_family=[["divide", "add"], ["divide", "add", "add"]],
        caveats="watch negative denominators",
    ),
    dict(
        name="cumulative_return_difference", semantic_intent="两只标的累计收益之差",
        problem_pattern="question asks the difference in percentage cumulative return between two entities (company vs index)",
        operand_roles="V1=ending value entity1; V2=base entity1 (usually 100); V3=ending value entity2; V4=base entity2 (usually 100)",
        procedure="1) compute each return as (end - base)/base; 2) subtract",
        formula="result = (V1-V2)/V2 - (V3-V4)/V4",
        template="subtract(divide(subtract(V1, V2), V2), divide(subtract(V3, V4), V4))",
        canonical_output_scale="fraction",
        unit_convention="bases are usually 100",
        program_family=[["subtract", "divide", "subtract", "divide", "subtract"]],
        caveats="if the question only asks WHICH is higher (comparison), gold may be direct greater(v1,v2) — check wording",
    ),
    dict(
        name="cumulative_return_ratio", semantic_intent="两只标的累计收益之比",
        problem_pattern="question asks the ratio of cumulative total returns between two entities",
        operand_roles="V1=ending entity1; V2=base entity1 (100); V3=ending entity2; V4=base entity2 (100)",
        procedure="compute (V1-V2)/(V3-V4)",
        formula="result = (V1-V2)/(V3-V4)",
        template="divide(subtract(V1, V2), subtract(V3, V4))",
        canonical_output_scale="fraction",
        unit_convention="bases usually 100",
        program_family=[["divide", "subtract", "subtract"]],
        caveats="same comparison-vs-ratio ambiguity as C18",
    ),
    dict(
        name="relative_return_points", semantic_intent="两个收益指数点差（基于100）",
        problem_pattern="question asks how much more return (in percentage points) one entity gained vs another",
        operand_roles="V1=end entity1; V2=base entity1 (100); V3=end entity2; V4=base entity2 (100)",
        procedure="(V1-V2) - (V3-V4)",
        formula="result = (V1-V2) - (V3-V4)",
        template="subtract(subtract(V1, V2), subtract(V3, V4))",
        canonical_output_scale="percentage points (not ×100)",
        unit_convention="bases usually 100",
        program_family=[["subtract", "subtract", "subtract"]],
        caveats="result may be negative",
    ),
    dict(
        name="growth_rate_projection", semantic_intent="按前段增长率外推未来值",
        problem_pattern="question asks a future value assuming the same rate of change as a previous period",
        operand_roles="V_current=most recent value; V_previous=prior-period value",
        procedure="growth factor = current/previous; project = current × factor",
        formula="result = current * (current / previous)",
        template="multiply(divide(V_current, V_previous), V_current)",
        canonical_output_scale="same units as inputs",
        unit_convention="constant multiplicative rate assumed",
        program_family=[["multiply", "divide"]],
        caveats="only valid for consecutive periods",
    ),
    dict(
        name="tax_effective_rate", semantic_intent="税前税后求有效税率",
        problem_pattern="question asks effective tax rate given pre-tax and after-tax amounts",
        operand_roles="V_pre=pre-tax amount; V_after=after-tax amount",
        procedure="(pre - after)/pre",
        formula="result = (pre - after)/pre",
        template="divide(subtract(V_pre, V_after), V_pre)",
        canonical_output_scale="fraction",
        unit_convention="same unit for both",
        program_family=[["divide", "subtract"]],
        caveats="tax is (pre-after), not after/pre",
    ),
    dict(
        name="basis_point_change", semantic_intent="两个百分比之间的基点差",
        problem_pattern="question asks change in basis points between two percentages",
        operand_roles="V_later, V_earlier = two percentage values (as numbers, e.g. 36 for 36%)",
        procedure="(later - earlier) × 10000",
        formula="result = (V_later - V_earlier) * 10000",
        template="multiply(subtract(V_later, V_earlier), const_10000)",
        canonical_output_scale="basis points (1 pp = 100 bp)",
        unit_convention="values given as percent numbers",
        program_family=[["multiply", "subtract"]],
        caveats="factor is 10000 not 100",
    ),
    dict(
        name="unit_convert_and_adjust", semantic_intent="单位换算后减去一子项",
        problem_pattern="question asks a value in a target unit after converting and subtracting a component",
        operand_roles="V1=value in original unit; const_unit=conversion; V2=component in target unit",
        procedure="convert V1 to target unit then subtract V2",
        formula="result = (V1 / factor) - V2",
        template="subtract(divide(V1, const_unit), V2)",
        canonical_output_scale="target unit",
        unit_convention="const_unit direction depends on source vs target (e.g. /1000 from millions to thousands... check header)",
        program_family=[["divide", "subtract"]],
        caveats="the official eval treats const_1000 as literal 1000 in subtract — mind the gold convention",
    ),
    dict(
        name="net_value_with_unit", semantic_intent="(值1 - 值2) × 单位因子",
        problem_pattern="question asks a value adjusted by an impact (e.g. excluding FX) then scaled to absolute units",
        operand_roles="V1=reported value; V2=impact/earlier value; const_unit=unit factor",
        procedure="subtract then multiply by unit factor",
        formula="result = (V1 - V2) * unit_factor",
        template="multiply(subtract(V1, V2), const_unit)",
        canonical_output_scale="base units after scaling",
        unit_convention="const_unit by header (thousands/millions)",
        program_family=[["multiply", "subtract"]],
        caveats="sign of impact matters",
    ),
    dict(
        name="derived_metric_change", semantic_intent="派生指标的变化（如经营费用=营收−营业利润）",
        problem_pattern="question asks change in a metric not directly in the table but derivable from two line items (e.g. operating expenses = sales - operating profit)",
        operand_roles="V1=line A later; V2=line B later; V3=line A earlier; V4=line B earlier",
        procedure="derive metric for each period (A - B), then subtract periods",
        formula="result = (V1-V2) - (V3-V4)",
        template="subtract(subtract(V1, V2), subtract(V3, V4))",
        canonical_output_scale="same units as inputs",
        unit_convention="—",
        program_family=[["subtract", "subtract", "subtract"]],
        caveats="confirm the derivation rule before applying",
    ),
    dict(
        name="sum_combined_vs_single", semantic_intent="合并量与单期值之差",
        problem_pattern="question asks how much more a combined value is than a single-period value",
        operand_roles="V1, V2 = components; V3 = single comparison value",
        procedure="(V1+V2) - V3",
        formula="result = (V1 + V2) - V3",
        template="subtract(add(V1, V2), V3)",
        canonical_output_scale="same units as inputs",
        unit_convention="—",
        program_family=[["add", "subtract"]],
        caveats="'more than' vs 'less than' changes order",
    ),
    dict(
        name="investment_return_value", semantic_intent="投资回报金额（份额 × 指数变动）",
        problem_pattern="question asks the dollar return on an initial investment given an index start and end value",
        operand_roles="V_invest=initial investment; V_start=index at start; V_end=index at end",
        procedure="units bought = invest/start; return = units × (end - start)",
        formula="result = (invest/start) * (end - start)",
        template="multiply(divide(V_invest, V_start), subtract(V_end, V_start))",
        canonical_output_scale="currency of investment",
        unit_convention="index values same scale",
        program_family=[["multiply", "divide", "subtract"]],
        caveats="this is absolute return, not percentage",
    ),
]

def main():
    # sample example questions from train by program_family
    train = fc.load_train()
    cats = {c["id"]: c for c in json.load(open("/home/tiantian/keyan/analysis/cat.json"))}
    by_struct = collections.defaultdict(list)
    for x in train:
        st = tuple(cats[x["id"]]["struct"]) if x["id"] in cats else ()
        if st:
            by_struct[st].append(x)
    rng = random.Random(20260816)

    out = []
    for i, s in enumerate(CANONICAL):
        ex = []
        for fam in s["program_family"]:
            for st in fam:
                pool = by_struct.get(tuple(st), [])
                if pool:
                    rng.shuffle(pool)
                    ex.append(pool[0]["qa"]["question"][:150])
        s2 = dict(s)
        s2["strategy_id"] = f"C{i+1:02d}"
        s2["example_questions"] = ex[:5]
        s2["retrieval_text"] = (
            f"Strategy: {s2['name']}\nSemantic: {s2['semantic_intent']}\n"
            f"Pattern: {s2['problem_pattern']}\nTemplate: {s2['template']}\n"
            f"Scale: {s2['canonical_output_scale']}\n"
            f"Example questions: " + " | ".join(ex[:5]))
        out.append(s2)

    path = os.path.join(config.OUT_DIR, "strategies_clean.json")
    json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
    print(f"cleaned strategies: {len(out)} -> {path}")
    for s in out:
        print(f"  {s['strategy_id']} {s['name']} | {s['template']} | family={len(s['program_family'])}")

    # 清洗前后对比日志（旧策略 -> 新策略）
    old = json.load(open(os.path.join(config.OUT_DIR, "strategies.json")))
    log = []
    for o in old:
        log.append({"old_id": o["strategy_id"], "old_name": o["name"],
                    "disposition": "MERGED", "note": "see clean pool"})
    json.dump(log, open(os.path.join(config.OUT_DIR, "strategy_clean_diff.json"), "w"), indent=1, ensure_ascii=False)
    print("wrote strategy_clean_diff.json (disposition log)")

if __name__ == "__main__":
    main()
