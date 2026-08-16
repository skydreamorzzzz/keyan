"""事实构造：论文的 RAG 与 Structured Mem0 事实分解（忠实于论文 III-B/III-G 描述）。

论文规定（无官方代码，以下为对论文文本的忠实实现 + 必要假设，全部标注）：
- RAG：pre-text 逐句 (PRE:)，table 行序列化为 attribute-value 对 (TABLE:)，post-text 逐行 (POST:)。
- Structured Mem0：仅 table 派生事实，schema = entity | column = value（论文例：`total volume|2021=637`），
  直接 embedding 存储（infer=False），无 LLM 抽取。

【假设 A】table 序列化：行首列 cell 为 entity，其余列 cell 按列头序列化为 `entity | col = val`。
【假设 B】structured 仅含 table 事实（论文明确 "table-derived entities"）。
【假设 C】composite filter：单元格规范化后若得到"单一数值"则 atomic 保留（含会计负数 -36 ( 36 ) -> -36）；
  若为复合值（范围/多数值/无数值）则判 composite 丢弃。此解释缓解"near-duplicate distractor"。
【假设 D】RAG 不做 composite filter（论文明确 RAG 无 composite-row filtering）。
"""
import re

def _clean_cell(cell):
    """单元格文本轻清理：去 $、去首尾空格。"""
    return str(cell).replace("$", "").strip()

def _parse_single_number(text):
    """尝试把单元格解析成单一数值；返回 (number, ok)。会计负数 -36 ( 36 ) -> -36。
    复合/范围/无数值 -> ok=False。"""
    t = text.replace(",", "").strip()
    if not t:
        return None, False
    # 会计负数：(-36) 或 -36 ( 36 ) 或 ( 36 )
    m = re.fullmatch(r"[-−]?\s*\(?(-?\d+(?:\.\d+)?)\)?\s*(?:\(\s*\d+(?:\.\d+)?\s*\))?\s*%?", t)
    if m:
        v = float(m.group(1))
        # 形如 "−36 ( 36 )"：第一个是负数
        return v, True
    # 百分比
    if t.endswith("%"):
        t2 = t[:-1].strip()
        try:
            return float(t2), True
        except ValueError:
            return None, False
    # 纯数字
    try:
        return float(t), True
    except ValueError:
        return None, False

def table_to_structured_facts(table, with_prefix=False):
    """table -> 结构化原子事实列表。每行：entity = row[0]，每列 -> entity | col = val。
    返回 list[dict{fact, entity, col, value_num, atomic}]。"""
    facts = []
    if not table:
        return facts
    header = table[0]
    for row in table[1:]:
        if not row:
            continue
        entity = _clean_cell(row[0])
        if not entity:
            continue
        for j, cell in enumerate(row[1:], start=1):
            col = header[j] if j < len(header) and str(header[j]).strip() else f"col{j}"
            val_raw = _clean_cell(cell)
            if not val_raw:
                continue
            num, ok = _parse_single_number(val_raw)
            fact = f"{entity} | {col} = {val_raw}"
            if with_prefix:
                fact = "TABLE: " + fact
            facts.append({"fact": fact, "entity": entity, "col": col,
                          "value_num": num, "atomic": ok, "raw": val_raw})
    return facts

def doc_to_rag_facts(pre_text, post_text, table):
    """完整文档 -> RAG 事实（PRE:/TABLE:/POST:）。"""
    facts = []
    for s in pre_text:
        s = s.strip()
        if s:
            facts.append({"fact": "PRE: " + s, "atomic": True, "type": "pre"})
    for row in table[1:] if table else []:
        if not row:
            continue
        entity = _clean_cell(row[0])
        header = table[0]
        for j, cell in enumerate(row[1:], start=1):
            col = header[j] if j < len(header) and str(header[j]).strip() else f"col{j}"
            val_raw = _clean_cell(cell)
            if val_raw:
                facts.append({"fact": f"TABLE: {entity} | {col} = {val_raw}",
                              "atomic": True, "type": "table",
                              "entity": entity, "col": col})
    for s in post_text:
        s = s.strip()
        if s:
            facts.append({"fact": "POST: " + s, "atomic": True, "type": "post"})
    return facts

def composite_filter(facts):
    """保留 atomic 事实，丢弃 composite（多数值/无数值）事实。论文【假设 C】。"""
    return [f for f in facts if f.get("atomic")]
