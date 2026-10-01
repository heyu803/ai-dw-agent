"""
Schema Linking 模块（对应方案 5.2 Schema Linking 模块）。

Schema Linking = 把"用户问题里的自然语言概念"对齐到"数仓里的具体表和字段"。
它紧接 RAG 召回之后：RAG 负责"召回候选表"，Schema Linking 负责
"从候选表里挑出真正需要的表/列，并整理成喂给 LLM 的紧凑结构"。

本实现分两步：
1. RAG 已召回 Top-K 候选表（见 graph 的 retrieve 节点）；
2. 这里把候选表压缩成紧凑 DDL 提示（to_ddl_hint），同时附上 join 关系提示，
   降低 LLM 生成 SQL 时的"幻觉字段 / 错连表"概率。
"""
from ..text_to_sql.state import SQLAgentState
from ...rag.pipeline import TableSchema

# 预置的表间 JOIN 关系提示（生产可从血缘图谱 Neo4j 自动推导）
JOIN_HINTS = {
    ("dwd_trade_order_detail", "dim_user"): "dwd_trade_order_detail.user_id = dim_user.user_id",
    ("dwd_trade_order_detail", "dim_product"): "dwd_trade_order_detail.product_id = dim_product.product_id",
    ("dwd_trade_order_detail", "dim_shop"): "dwd_trade_order_detail.shop_id = dim_shop.shop_id",
}


def build_linked_schema(tables: list[TableSchema]) -> str:
    """把候选表整理成紧凑 DDL 提示 + JOIN 关系，供 LLM 使用。"""
    parts = [t.to_ddl_hint() for t in tables]

    names = {t.name for t in tables}
    hints = []
    for (a, b), cond in JOIN_HINTS.items():
        if a in names and b in names:
            hints.append(f"-- JOIN: {cond}")
    if hints:
        parts.append("\n".join(hints))

    return "\n\n".join(parts)


def schema_linking_node(state: SQLAgentState) -> SQLAgentState:
    tables = state.get("retrieved_tables", [])
    linked = build_linked_schema(tables)
    state["linked_schema"] = linked
    state.setdefault("trace", []).append(
        f"[Step3 Schema Linking] 选定 {len(tables)} 张表: {', '.join(t.name for t in tables)}"
    )
    return state
