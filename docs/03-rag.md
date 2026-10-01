# 三、RAG 知识库系统设计

> 对应原方案第三章。本章讲清楚：为什么 Text-to-SQL 需要 RAG、知识库里存什么、怎么检索、以及面试高频的 **RRF 融合重排**。

## 3.1 为什么 Text-to-SQL 需要 RAG

一个真实数仓有成百上千张表、上万个字段。如果把所有表结构都塞进 Prompt：
- **超出上下文窗口**，成本爆炸；
- **干扰模型**，无关表越多生成的 SQL 越容易出错（"大海捞针"问题）。

所以正确做法是：先用 RAG **召回与当前问题最相关的少数几张表**，只把这些表的结构喂给 LLM。这就是 RAG 在 Text-to-SQL 里的核心价值——**精准的 Schema 召回**。

本项目把"表结构"作为知识库的文档单元。每张表生成一段自然语言描述（表名、业务含义、字段列表），向量化后建索引。查询时召回 Top-K 张候选表。

- 对应代码：`src/rag/pipeline.py`（`TableSchema` / `SchemaKnowledgeBase`）

## 3.2 数据接入与分块策略

原方案用 RAGFlow 做文档解析与分块。本项目场景是结构化的表元数据，**分块策略简化为"一张表一个 chunk"**，因为表是天然的语义单元。

> **面试点**：分块（chunking）策略要点——块太大则召回不精准、块太小则语义破碎。对文档类内容常用"按语义/标题分块 + 重叠窗口"；对结构化元数据则按天然单元（表/字段）分块。

`TableSchema.to_document_content()` 把表渲染成一段便于检索的文本；`to_ddl_hint()` 把表渲染成喂给 LLM 的 DDL 提示。这两者分离，是因为"用于检索的文本"和"用于生成的上下文"诉求不同。

## 3.3 向量检索与 Re-ranking（核心）

单一的向量检索（语义相似）有个弱点：**对精确关键词不敏感**。比如用户问"dws_trade_order_di 的订单量"，向量检索可能因为语义泛化而漏掉这张精确命名的表。反过来，纯关键词检索（如 BM25）又对语义同义词不敏感。

**解法：混合检索（Hybrid Search）= 向量检索 + 关键词检索，再用 RRF 融合两路结果。**

本项目 `src/rag/reranker.py` 实现了三个函数：
- `keyword_search()`：BM25 近似的关键词打分；
- `rrf_fuse()`：RRF 融合；
- `hybrid_retrieve()`：先各自检索，再 RRF 融合重排。

### RRF 融合算法实现

RRF（Reciprocal Rank Fusion，倒数排名融合）的核心公式：

```
score(d) = Σ  1 / (k + rank_i(d))
          i∈检索器
```

其中：
- `d` 是某个文档；
- `rank_i(d)` 是文档 `d` 在第 `i` 个检索器结果中的**排名**（从 1 开始）；
- `k` 是平滑常数，**经验值取 60**；
- 多路检索器各自给出排名，对同一文档的倒数排名求和，得分越高越靠前。

**为什么用排名而不是用原始分数？** 因为不同检索器的分数量纲不同（余弦相似度 0~1，BM25 可能是 0~几十），直接相加没有意义。RRF 只用"排名"这个统一量纲，**无需归一化**就能融合异构检索器，这是它简单又好用的关键。

```python
# 简化示意（完整实现见 src/rag/reranker.py）
def rrf_fuse(rank_lists, k=60):
    scores = {}
    for ranked in rank_lists:              # 每个检索器的有序结果
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank)
    return sorted(scores, key=scores.get, reverse=True)
```

> **面试点**：被问"如何融合多路召回"时，RRF 是最干净的标准答案。能说出"用排名而非原始分数，因此免归一化、对异构检索器鲁棒，k 取 60"就非常加分。生产里还会在 RRF 之后再接一个 **Cross-Encoder 精排**（如 BGE-Reranker）做最终重排。

## 3.4 知识库更新机制

表结构会随数仓演进而变化（加字段、改注释、废弃表）。生产里需要：
- **增量更新**：表元数据变更时只重新向量化受影响的表；
- **版本与时效**：记录每个 chunk 的版本和更新时间，支持灰度；
- **一致性**：DDL 变更事件驱动（如监听元数据中心 / CDC）触发重建索引。

本项目用 `SchemaKnowledgeBase.index_table()` 做内存级建索引，生产可替换为"事件驱动 + Milvus upsert"。

## 关键文件索引

- `src/rag/embedding.py`：轻量 embedding（字符 n-gram 哈希，生产换 BGE-M3）
- `src/rag/vector_store.py`：内置向量库 + 工厂（生产换 Milvus）
- `src/rag/reranker.py`：关键词检索 + **RRF 融合**
- `src/rag/pipeline.py`：Schema 知识库（建索引 + 召回）
