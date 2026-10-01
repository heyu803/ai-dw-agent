"""
RAG Pipeline（对应方案 3.1 知识库整体架构 / 3.2 数据接入与分块策略）。

在 Text-to-SQL 场景里，RAG 的"知识库"就是数仓的元数据（Schema 文档）：
每张表 = 一个文档（chunk），内容包含表名、业务含义、字段列表与注释、示例。

为什么用 RAG 而不是把所有表结构塞进 Prompt（面试高频）：
- 真实数仓动辄上千张表，全量 Schema 远超上下文窗口、且稀释注意力、烧 Token；
- 用 RAG 先召回"与问题最相关的少数几张表"，再喂给 LLM 做 Schema Linking 与生成，
  既省 Token 又显著提升准确率。这就是 3.2 的"数据接入与分块策略"落地。
"""
from dataclasses import dataclass
from .vector_store import build_vector_store, Document


@dataclass
class TableSchema:
    name: str
    description: str
    columns: list[tuple[str, str, str]]  # (列名, 类型, 注释)

    def to_document_content(self) -> str:
        cols = "; ".join(f"{c}({t}) {desc}" for c, t, desc in self.columns)
        return f"表名: {self.name}。业务含义: {self.description}。字段: {cols}"

    def to_ddl_hint(self) -> str:
        """喂给 LLM 的紧凑 DDL 提示。"""
        lines = [f"-- {self.description}", f"TABLE {self.name} ("]
        lines += [f"  {c} {t},  -- {desc}" for c, t, desc in self.columns]
        lines.append(")")
        return "\n".join(lines)


class SchemaKnowledgeBase:
    """数仓元数据知识库：建库 + 混合检索。"""

    def __init__(self):
        self.store = build_vector_store()
        self.tables: dict[str, TableSchema] = {}

    def index_table(self, table: TableSchema):
        self.tables[table.name] = table
        self.store.add(Document(
            doc_id=table.name,
            content=table.to_document_content(),
            metadata={"table": table.name},
        ))

    def retrieve_tables(self, question: str, top_k: int = 3) -> list[TableSchema]:
        """根据问题混合检索最相关的表（向量 + 关键词 + RRF）。"""
        from .reranker import hybrid_retrieve
        hits = hybrid_retrieve(self.store, question, top_k=top_k)
        return [self.tables[doc.metadata["table"]] for doc, _ in hits]
