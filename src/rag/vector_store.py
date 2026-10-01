"""
向量库抽象（对应方案 2.1 选型：Milvus）。

接口稳定、实现可换：
- BuiltinVectorStore：内存/进程内实现，零依赖，用于 demo 与小规模；
- MilvusVectorStore（占位）：生产用 Milvus，支持十亿级向量、混合检索、高可用集群。

文档（document）模型：每条记录代表知识库里的一个"块"，
在本项目里就是一张数仓表的 schema 描述。
"""
from dataclasses import dataclass, field
from .embedding import embed, cosine


@dataclass
class Document:
    doc_id: str
    content: str                       # 用于向量化与展示的文本
    metadata: dict = field(default_factory=dict)
    vector: list[float] = field(default_factory=list)


class BuiltinVectorStore:
    """进程内向量库：足够演示召回与排序，不适合大规模。"""

    def __init__(self):
        self._docs: list[Document] = []

    def add(self, doc: Document):
        if not doc.vector:
            doc.vector = embed(doc.content)
        self._docs.append(doc)

    def search(self, query: str, top_k: int = 5) -> list[tuple[Document, float]]:
        qv = embed(query)
        scored = [(d, cosine(qv, d.vector)) for d in self._docs]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    @property
    def documents(self) -> list[Document]:
        return self._docs


def build_vector_store():
    """工厂：根据配置返回向量库实现。"""
    from ..config import get_settings
    s = get_settings()
    if s.vector_store == "milvus":
        # 生产：from pymilvus import MilvusClient ...
        # 这里保留扩展点，demo 默认走 builtin
        raise NotImplementedError(
            "Milvus 接入请安装 pymilvus 并实现 MilvusVectorStore；demo 请用 VECTOR_STORE=builtin"
        )
    return BuiltinVectorStore()
