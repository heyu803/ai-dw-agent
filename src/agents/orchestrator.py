"""
Orchestrator 编排器（对应方案"Agent 编排层 Core"）。

职责：作为应用层的统一门面（Facade），负责：
1. 一次性装配重型依赖（LLM Gateway、RAG 知识库、各 Agent 图）；
2. 把请求路由到对应 Agent（这里聚焦 Text-to-SQL 与 DQ）；
3. 把内部 State 转换成对外的 QueryResult 数据契约。

生产里 Orchestrator 还会做：任务调度、多 Agent 协作、Tool Registry 工具注册中心。
"""
from .text_to_sql.graph import build_sql_agent
from .text_to_sql.state import SQLAgentState
from ..llm_gateway.gateway import build_gateway
from ..rag.pipeline import SchemaKnowledgeBase
from ..warehouse_schema import TABLES
from ..schemas.models import QueryResult


class Orchestrator:
    def __init__(self):
        # 1. LLM Gateway
        self.gateway = build_gateway()
        # 2. RAG 知识库：把数仓元数据建索引
        self.kb = SchemaKnowledgeBase()
        for t in TABLES:
            self.kb.index_table(t)
        # 3. Text-to-SQL Agent（编译好的 LangGraph）
        self.sql_agent = build_sql_agent(self.gateway, self.kb)

    def run_text_to_sql(self, question: str, session_id: str = "default") -> QueryResult:
        init: SQLAgentState = {"question": question, "session_id": session_id, "trace": []}
        final = self.sql_agent.invoke(init)
        return QueryResult(
            success=bool(final.get("success")),
            question=question,
            sql=final.get("sql"),
            columns=final.get("columns", []),
            rows=final.get("rows", []),
            row_count=final.get("row_count", 0),
            answer=final.get("answer"),
            validations=final.get("validations", []),
            retry_count=final.get("retry_count", 0),
            error=final.get("error"),
            trace=final.get("trace", []),
        )


# 单例（FastAPI 启动时构建一次）
_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
