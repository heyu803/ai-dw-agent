"""
SQL 生成核心逻辑（对应方案 5.3.1 SQL 生成核心逻辑）。

职责：
- 首次生成：用 sql_generation Prompt + Schema Linking 结果生成 SQL；
- 修正重试：当校验失败时，用 sql_fix Prompt 携带"上一版 SQL + 校验错误"重生成，
  这就是图（image 3/4）里的 "LLM 修正生成 携带错误上下文"。
- 解析 LLM 输出中的 ```sql ``` 代码块，做鲁棒抽取。
"""
import re
from ..text_to_sql.state import SQLAgentState
from ...llm_gateway.gateway import LLMGateway


def _extract_sql(text: str) -> str:
    """从 LLM 输出里抽取 SQL（兼容 ```sql ``` 包裹、裸 SQL 两种情况）。"""
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    sql = m.group(1) if m else text
    return sql.strip().rstrip(";").strip()


def make_generate_node(gateway: LLMGateway):
    def generate_sql_node(state: SQLAgentState) -> SQLAgentState:
        question = state.get("rewritten_question") or state["question"]
        schema = state.get("linked_schema", "")
        retry = state.get("retry_count", 0)

        if retry == 0:
            raw = gateway.complete_with_prompt(
                "sql_generation", question=question, schema=schema
            )
            step = "[Step4 生成SQL] 首次生成"
        else:
            errors = "\n".join(
                f"- [{v.layer}/{v.severity}] {v.message}"
                for v in state.get("validations", [])
                if v.severity in ("ERROR", "BLOCKER", "WARN")
            )
            raw = gateway.complete_with_prompt(
                "sql_fix",
                question=question,
                schema=schema,
                previous_sql=state.get("sql", ""),
                errors=errors,
            )
            step = f"[Step4 修正SQL] 第 {retry} 次重试（携带错误上下文）"

        sql = _extract_sql(raw)
        state["sql"] = sql
        state.setdefault("trace", []).append(f"{step}: {sql}")
        return state

    return generate_sql_node
