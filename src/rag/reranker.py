"""
混合检索 + Re-ranking（对应方案 3.3 向量检索与 Re-ranking，含 RRF 融合算法实现）。

Text-to-SQL 里"召回正确的表"至关重要，单一召回容易漏：
- 向量召回：擅长语义近似（"营业额" ~ "支付金额"），但对精确术语弱；
- 关键词召回（BM25 式）：擅长精确匹配表名/字段名，但对同义改写弱。
所以做 Hybrid Search，再用 RRF（Reciprocal Rank Fusion）融合两路排名。

RRF 公式：score(d) = Σ_i  1 / (k + rank_i(d))
- k 为平滑常数（论文常用 60），rank 从 1 开始；
- 只依赖"名次"而非各路打分的绝对量纲，天然解决不同检索器分数不可比的问题。
"""
import re
from collections import defaultdict
from .vector_store import BuiltinVectorStore, Document


def keyword_search(store: BuiltinVectorStore, query: str, top_k: int = 5) -> list[tuple[Document, float]]:
    """极简 BM25 近似：按 query 词在文档中的命中次数打分（演示用）。"""
    terms = [t for t in re.split(r"[\s,，、]+", query.lower()) if t]
    scored = []
    for d in store.documents:
        text = d.content.lower()
        score = sum(text.count(t) for t in terms if t)
        if score > 0:
            scored.append((d, float(score)))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def rrf_fuse(
    ranked_lists: list[list[tuple[Document, float]]],
    k: int = 60,
    top_k: int = 5,
) -> list[tuple[Document, float]]:
    """对多路召回结果做 RRF 融合，返回融合后 Top-K。"""
    fused: dict[str, float] = defaultdict(float)
    doc_map: dict[str, Document] = {}
    for ranked in ranked_lists:
        for rank, (doc, _score) in enumerate(ranked, start=1):
            fused[doc.doc_id] += 1.0 / (k + rank)
            doc_map[doc.doc_id] = doc
    result = [(doc_map[did], s) for did, s in fused.items()]
    result.sort(key=lambda x: x[1], reverse=True)
    return result[:top_k]


def hybrid_retrieve(store: BuiltinVectorStore, query: str, top_k: int = 5) -> list[tuple[Document, float]]:
    """向量召回 + 关键词召回 -> RRF 融合 -> Top-K。"""
    vec_hits = store.search(query, top_k=top_k * 2)
    kw_hits = keyword_search(store, query, top_k=top_k * 2)
    return rrf_fuse([vec_hits, kw_hits], top_k=top_k)
