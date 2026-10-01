"""
Text-to-SQL Agent 的状态定义（对应方案 5.1 Agent 状态机设计 / LangGraph）。

LangGraph 的核心思想（面试必讲）：
- 把 Agent 建模成"状态机 / 有向图"，节点是处理步骤，边是流转关系；
- 用一个共享的 State（这里是 TypedDict）在节点间传递，每个节点读 State、写 State；
- 支持条件边（conditional edges）实现"校验失败则回到生成节点重试"这种循环，
  这正是方案选 LangGraph 而非 CrewAID 的关键理由（ADR-002：支持循环/条件分支/人工介入）。
"""
from typing import TypedDict
from ...rag.pipeline import TableSchema
from ...schemas.models import ValidationResult


class SQLAgentState(TypedDict, total=False):
    # 输入
    question: str                      # 用户原始问题
    session_id: str

    # 处理过程中的中间产物
    rewritten_question: str            # Step1 查询改写后的问题
    retrieved_tables: list[TableSchema]  # Step2 RAG 召回的相关表
    linked_schema: str                 # Step3 Schema Linking 后的紧凑 DDL 提示
    sql: str                           # Step4 生成的 SQL
    validations: list[ValidationResult]  # Step5 五层校验结果
    validation_ok: bool                # 校验是否整体通过
    retry_count: int                   # 已重试次数（对应图中 retry_count）

    # 执行与输出
    columns: list[str]
    rows: list[list]
    row_count: int
    answer: str                        # Step7 自然语言总结
    error: str
    success: bool

    # 全链路轨迹（教学/可观测性）
    trace: list[str]
