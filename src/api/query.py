"""Query Service —— Text-to-SQL 查询 API（对应应用服务层 BFF 的 Query Service）。"""
from fastapi import APIRouter
from ..schemas.models import QueryRequest, QueryResult
from ..agents.orchestrator import get_orchestrator

router = APIRouter(prefix="/api/v1/query", tags=["Text-to-SQL"])


@router.post("/generate", response_model=QueryResult, summary="自然语言查询数仓")
def generate(req: QueryRequest) -> QueryResult:
    """
    对应方案 image 2 的完整调用时序：
    自然语言问题 -> 改写 -> RAG 检索 Schema -> Schema Linking -> 生成 SQL
    -> 五层自校验 -> 只读沙箱执行 -> 自然语言总结 -> 返回。
    """
    return get_orchestrator().run_text_to_sql(req.question, req.session_id)
