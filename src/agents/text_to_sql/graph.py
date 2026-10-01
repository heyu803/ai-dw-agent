"""
Text-to-SQL Agent 状态机（LangGraph 编排，对应方案 5.1 + 图2 完整调用时序）。

整张图的流转（与 image 2 时序图、image 3/4 校验流程一一对应）：

    START
      │
   rewrite          Step1 查询改写
      │
   retrieve         Step2 RAG 检索 Schema（向量+关键词+RRF）
      │
   schema_link      Step3 Schema Linking
      │
   generate ◀──────┐  Step4 生成SQL / 修正SQL（携带错误上下文）
      │            │
   validate        │  Step5 五层自校验
      │            │
   ┌──┴──┐         │
   │route│─────────┘  ERROR 且 retry<N -> 回到 generate
   │     │
   ├─ validation_ok ─▶ execute   Step6 只读沙箱执行 ─▶ format Step7 自然语言总结 ─▶ END
   │
   └─ BLOCKER / 重试耗尽 ─▶ return_error ─▶ END

条件边（route_after_validate）正是 LangGraph 相对其它框架的杀手锏：原生支持"带循环的有向图"。
"""
from langgraph.graph import StateGraph, START, END

from .state import SQLAgentState
from .schema_linking import schema_linking_node
from .sql_generator import make_generate_node
from .validator import make_validate_node
from .sandbox import execute_node
from ...llm_gateway.gateway import LLMGateway
from ...rag.pipeline import SchemaKnowledgeBase
from ...schemas.models import ValidationSeverity
from ...config import get_settings


# ---------- 各节点 ----------
def make_rewrite_node():
    def rewrite_node(state: SQLAgentState) -> SQLAgentState:
        # Step1 查询改写：demo 直接透传；生产可做指代消解、口径补全、多轮上下文融合
        q = state["question"]
        state["rewritten_question"] = q
        state["retry_count"] = state.get("retry_count", 0)
        state.setdefault("trace", []).append(f"[Step1 查询改写] {q}")
        return state
    return rewrite_node


def make_retrieve_node(kb: SchemaKnowledgeBase):
    def retrieve_node(state: SQLAgentState) -> SQLAgentState:
        q = state.get("rewritten_question") or state["question"]
        tables = kb.retrieve_tables(q, top_k=3)
        state["retrieved_tables"] = tables
        state.setdefault("trace", []).append(
            f"[Step2 RAG召回] 候选表: {', '.join(t.name for t in tables)}"
        )
        return state
    return retrieve_node


def make_format_node(gateway: LLMGateway):
    def format_node(state: SQLAgentState) -> SQLAgentState:
        sample = state.get("rows", [])[:3]
        answer = gateway.complete_with_prompt(
            "answer_summary",
            question=state["question"],
            row_count=state.get("row_count", 0),
            columns=", ".join(state.get("columns", [])),
            sample=str(sample),
        )
        state["answer"] = answer
        state.setdefault("trace", []).append("[Step7 结果格式化] 已生成自然语言总结")
        return state
    return format_node


def return_error_node(state: SQLAgentState) -> SQLAgentState:
    blockers = [v for v in state.get("validations", []) if v.severity == ValidationSeverity.BLOCKER]
    errors = [v for v in state.get("validations", []) if v.severity == ValidationSeverity.ERROR]
    if blockers:
        msg = "；".join(v.message for v in blockers)
        state["error"] = f"安全拦截：{msg}"
    elif errors:
        msg = "；".join(v.message for v in errors)
        state["error"] = f"重试 {state.get('retry_count', 0)} 次后仍未通过校验：{msg}"
    else:
        state["error"] = state.get("error") or "未知错误"
    state["success"] = False
    state.setdefault("trace", []).append(f"[终止] {state['error']}")
    return state


# ---------- 条件边路由（只读 state，不做任何修改）----------
def route_after_validate(state: SQLAgentState) -> str:
    validations = state.get("validations", [])
    has_blocker = any(v.severity == ValidationSeverity.BLOCKER for v in validations)
    if has_blocker:
        return "blocked"                      # -> return_error（不重试）
    if state.get("validation_ok"):
        return "ok"                            # -> execute
    # 存在 ERROR：判断是否还能重试（注意：路由函数不能修改 state，
    # 否则在 LangGraph 中修改不会被持久化，会导致 retry_count 永不递增的死循环）
    if state.get("retry_count", 0) < get_settings().sql_max_retry:
        return "retry"                         # -> prepare_retry -> generate
    return "exhausted"                          # -> return_error


def prepare_retry_node(state: SQLAgentState) -> SQLAgentState:
    """专门递增 retry_count 的节点（在节点里改 state 才会被持久化）。"""
    state["retry_count"] = state.get("retry_count", 0) + 1
    state.setdefault("trace", []).append(f"[重试准备] retry_count -> {state['retry_count']}")
    return state


def route_after_execute(state: SQLAgentState) -> str:
    return "ok" if state.get("success") else "failed"


# ---------- 组装图 ----------
def build_sql_agent(gateway: LLMGateway, kb: SchemaKnowledgeBase):
    builder = StateGraph(SQLAgentState)

    builder.add_node("rewrite", make_rewrite_node())
    builder.add_node("retrieve", make_retrieve_node(kb))
    builder.add_node("schema_link", schema_linking_node)
    builder.add_node("generate", make_generate_node(gateway))
    builder.add_node("validate", make_validate_node(gateway))
    builder.add_node("prepare_retry", prepare_retry_node)
    builder.add_node("execute", execute_node)
    builder.add_node("format", make_format_node(gateway))
    builder.add_node("return_error", return_error_node)

    builder.add_edge(START, "rewrite")
    builder.add_edge("rewrite", "retrieve")
    builder.add_edge("retrieve", "schema_link")
    builder.add_edge("schema_link", "generate")
    builder.add_edge("generate", "validate")

    builder.add_conditional_edges(
        "validate", route_after_validate,
        {"ok": "execute", "retry": "prepare_retry", "blocked": "return_error", "exhausted": "return_error"},
    )
    builder.add_edge("prepare_retry", "generate")
    builder.add_conditional_edges(
        "execute", route_after_execute,
        {"ok": "format", "failed": "return_error"},
    )
    builder.add_edge("format", END)
    builder.add_edge("return_error", END)

    return builder.compile()
