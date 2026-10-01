"""
只读执行沙箱（对应方案 5.4 执行沙箱设计 + 图中"只读沙箱执行"）。

沙箱要做的事（面试可讲，体现工程严谨性）：
1. 只读连接：用只读账号/只读库，杜绝任何写操作落到生产；
2. 强制 LIMIT：对结果集兜底截断，防止误查千万行把内存打爆；
3. 超时控制：避免慢查询拖垮服务（SQLite 这里用 statement timeout 思路演示）；
4. 资源隔离：生产应在独立的查询引擎/资源队列里执行（如 Presto 只读集群）。

本 demo 用 SQLite 演示，强制注入 LIMIT 并捕获执行异常。
"""
import re
import sqlite3
import sqlglot
from sqlglot import exp

from ..text_to_sql.state import SQLAgentState
from ...config import get_settings


def _ensure_limit(sql: str, limit: int) -> str:
    """若 SQL 没有 LIMIT，则强制注入一个 LIMIT，防止大结果集。"""
    try:
        parsed = sqlglot.parse_one(sql, read="sqlite")
        if parsed.find(exp.Limit) is None:
            parsed = parsed.limit(limit)
        return parsed.sql(dialect="sqlite")
    except Exception:  # noqa: BLE001
        # 解析失败兜底：用正则判断
        if not re.search(r"\blimit\b", sql, re.IGNORECASE):
            return f"{sql.rstrip(';')} LIMIT {limit}"
        return sql


def execute_node(state: SQLAgentState) -> SQLAgentState:
    s = get_settings()
    sql = _ensure_limit(state["sql"], s.sql_result_limit)
    state["sql"] = sql  # 回写注入 LIMIT 后的 SQL，便于展示真实执行体

    try:
        # 只读模式打开（file:...?mode=ro），任何写操作都会报错 —— 沙箱的关键保障
        uri = f"file:{s.sqlite_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        conn.close()

        state["columns"] = cols
        state["rows"] = [list(r) for r in rows]
        state["row_count"] = len(rows)
        state["success"] = True
        state.setdefault("trace", []).append(
            f"[Step6 沙箱执行] 成功，返回 {len(rows)} 行（已强制 LIMIT {s.sql_result_limit}）"
        )
    except Exception as e:  # noqa: BLE001
        state["success"] = False
        state["error"] = f"执行失败: {e}"
        state.setdefault("trace", []).append(f"[Step6 沙箱执行] 失败: {e}")
    return state
