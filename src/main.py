"""
FastAPI 应用入口（对应方案 2.1 后端框架选型：FastAPI）。

为什么选 FastAPI（ADR 风格回答）：异步高性能、基于类型注解自动生成 OpenAPI 文档、
Pydantic 原生集成、生态丰富。启动后访问 http://localhost:8000/docs 可交互式调试。
"""
import logging
from fastapi import FastAPI
from .api import query as query_api
from .api import dq as dq_api

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")

app = FastAPI(
    title="AI 数仓 Agent",
    description="Text-to-SQL Agent + 数据质量治理 Agent（基于 LangGraph + RAG + LLM Gateway）",
    version="2.0.0",
)

app.include_router(query_api.router)
app.include_router(dq_api.router)


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "AI 数仓 Agent",
        "docs": "/docs",
        "endpoints": [
            "POST /api/v1/query/generate  自然语言查数仓",
            "POST /api/v1/dq/check        数据质量规则检测",
            "POST /api/v1/dq/root-cause   异常根因分析",
        ],
    }


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
