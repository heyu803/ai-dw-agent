"""
多层自校验引擎（对应方案 5.3.2 多层自校验引擎 + 图3/4 的"校验·重试决策"流程）。

为什么 Text-to-SQL 必须自校验（面试核心论点）：
LLM 生成的 SQL 有三类典型风险 ——
  ① 语法错误（跑不起来）、② 字段/表幻觉（编了不存在的列）、
  ③ 危险操作（DROP/DELETE）、④ 语义跑偏（能跑但答非所问）、⑤ 性能炸裂（全表扫描）。
所以在"执行前"加一道五层校验，把大部分问题拦在沙箱之外，并能携带错误上下文让 LLM 自我修正。

五层（由轻到重、由确定到模糊）：
  L1 语法校验  —— sqlglot 能否解析（ERROR）
  L2 Schema校验 —— 表/列是否真实存在（ERROR）
  L3 安全校验  —— 只读？禁 DROP/DELETE/...？（BLOCKER，命中即拒绝，不重试）
  L4 语义校验  —— LLM 判断 SQL 是否回答了问题（WARN）
  L5 性能校验  —— SELECT */缺 LIMIT/缺分区过滤（WARN）

严重级别决定后续走向（见 graph 的条件边）：
  BLOCKER -> 直接返回错误（对应图中 "BLOCKER -> 直接返回错误 显示具体错误"）
  ERROR   -> retry_count < N 则带错误上下文重试，否则返回错误
  WARN    -> 不阻断，记录风险后继续执行
"""
import re
import sqlglot
from sqlglot import exp

from ...schemas.models import ValidationResult, ValidationLayer, ValidationSeverity
from ...warehouse_schema import TABLES_BY_NAME
from ..text_to_sql.state import SQLAgentState
from ...llm_gateway.gateway import LLMGateway

DANGEROUS = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|INSERT|UPDATE|ALTER|CREATE|REPLACE|GRANT|MERGE)\b",
    re.IGNORECASE,
)
DIALECT = "sqlite"


# ---------- L1 语法 ----------
def check_syntax(sql: str):
    try:
        parsed = sqlglot.parse_one(sql, read=DIALECT)
        return parsed, ValidationResult(
            layer=ValidationLayer.SYNTAX, severity=ValidationSeverity.PASS, message="语法解析通过"
        )
    except Exception as e:  # noqa: BLE001
        return None, ValidationResult(
            layer=ValidationLayer.SYNTAX, severity=ValidationSeverity.ERROR,
            message="SQL 语法解析失败", detail=str(e),
        )


# ---------- L2 Schema ----------
def check_schema(parsed) -> ValidationResult:
    if parsed is None:
        return ValidationResult(
            layer=ValidationLayer.SCHEMA, severity=ValidationSeverity.PASS,
            message="语法未通过，跳过 Schema 校验",
        )
    used_tables = {t.name for t in parsed.find_all(exp.Table)}
    unknown_tables = [t for t in used_tables if t not in TABLES_BY_NAME]
    if unknown_tables:
        return ValidationResult(
            layer=ValidationLayer.SCHEMA, severity=ValidationSeverity.ERROR,
            message=f"引用了不存在的表: {', '.join(unknown_tables)}",
        )

    # 收集这些表的全部合法列
    valid_cols = set()
    for tname in used_tables:
        for c, _t, _d in TABLES_BY_NAME[tname].columns:
            valid_cols.add(c.lower())

    # 收集查询里定义的别名（SELECT ... AS alias / 子查询别名），这些不是真实列，需排除
    aliases = {a.alias.lower() for a in parsed.find_all(exp.Alias) if a.alias}

    bad_cols = []
    for col in parsed.find_all(exp.Column):
        name = col.name.lower()
        if name == "*" or name in aliases:
            continue
        if name not in valid_cols:
            bad_cols.append(col.name)
    if bad_cols:
        return ValidationResult(
            layer=ValidationLayer.SCHEMA, severity=ValidationSeverity.ERROR,
            message=f"引用了不存在的字段: {', '.join(sorted(set(bad_cols)))}",
            detail=f"可用字段: {', '.join(sorted(valid_cols))}",
        )
    return ValidationResult(
        layer=ValidationLayer.SCHEMA, severity=ValidationSeverity.PASS, message="表/字段均存在",
    )


# ---------- L3 安全（最高优先级，命中即 BLOCKER）----------
def check_security(sql: str, parsed) -> ValidationResult:
    # 防多语句注入
    if len([s for s in sql.split(";") if s.strip()]) > 1:
        return ValidationResult(
            layer=ValidationLayer.SECURITY, severity=ValidationSeverity.BLOCKER,
            message="检测到多条语句，疑似注入，已拒绝",
        )
    # 关键词正则（防御纵深：即便 AST 没解析出来也能拦）
    if DANGEROUS.search(sql):
        kw = DANGEROUS.search(sql).group(1).upper()
        return ValidationResult(
            layer=ValidationLayer.SECURITY, severity=ValidationSeverity.BLOCKER,
            message=f"检测到危险操作 {kw}，只读环境拒绝执行",
        )
    # AST 层：必须是 SELECT
    if parsed is not None and not isinstance(parsed, (exp.Select, exp.Union, exp.Subquery)):
        return ValidationResult(
            layer=ValidationLayer.SECURITY, severity=ValidationSeverity.BLOCKER,
            message=f"非查询语句({type(parsed).__name__})，只读环境拒绝执行",
        )
    return ValidationResult(
        layer=ValidationLayer.SECURITY, severity=ValidationSeverity.PASS, message="只读安全校验通过",
    )


# ---------- L4 语义（LLM 判定）----------
def check_semantic(sql: str, question: str, gateway: LLMGateway) -> ValidationResult:
    import json
    try:
        raw = gateway.complete_with_prompt("semantic_check", question=question, sql=sql)
        data = json.loads(re.search(r"\{.*\}", raw, re.DOTALL).group(0))
        if data.get("match"):
            return ValidationResult(
                layer=ValidationLayer.SEMANTIC, severity=ValidationSeverity.PASS,
                message="语义匹配", detail=data.get("reason"),
            )
        return ValidationResult(
            layer=ValidationLayer.SEMANTIC, severity=ValidationSeverity.WARN,
            message="语义可能跑偏", detail=data.get("reason"),
        )
    except Exception as e:  # noqa: BLE001
        return ValidationResult(
            layer=ValidationLayer.SEMANTIC, severity=ValidationSeverity.PASS,
            message="语义校验跳过（解析异常，不阻断）", detail=str(e),
        )


# ---------- L5 性能 ----------
def check_performance(sql: str, parsed) -> ValidationResult:
    warns = []
    if re.search(r"select\s+\*", sql, re.IGNORECASE):
        warns.append("使用 SELECT * 可能拉取过多列")
    if parsed is not None:
        used_tables = {t.name for t in parsed.find_all(exp.Table)}
        # 查询了明细大表却没有 LIMIT 也没有聚合，提示风险
        big = "dwd_trade_order_detail"
        if big in used_tables:
            has_limit = bool(parsed.find(exp.Limit))
            has_group = bool(parsed.find(exp.Group))
            if not has_limit and not has_group:
                warns.append(f"查询明细大表 {big} 未加 LIMIT/聚合，存在全表扫描风险")
    if warns:
        return ValidationResult(
            layer=ValidationLayer.PERFORMANCE, severity=ValidationSeverity.WARN,
            message="性能风险提示", detail="; ".join(warns),
        )
    return ValidationResult(
        layer=ValidationLayer.PERFORMANCE, severity=ValidationSeverity.PASS, message="无明显性能风险",
    )


# ---------- 组装为图节点 ----------
def make_validate_node(gateway: LLMGateway):
    def validate_node(state: SQLAgentState) -> SQLAgentState:
        sql = state["sql"]
        question = state.get("rewritten_question") or state["question"]

        parsed, r1 = check_syntax(sql)
        results = [r1]
        # 安全永远跑（防御纵深）
        results.append(check_security(sql, parsed))
        # 语法通过才继续后续层
        if parsed is not None:
            results.append(check_schema(parsed))
            results.append(check_semantic(sql, question, gateway))
            results.append(check_performance(sql, parsed))

        state["validations"] = results
        has_blocker = any(r.severity == ValidationSeverity.BLOCKER for r in results)
        has_error = any(r.severity == ValidationSeverity.ERROR for r in results)
        state["validation_ok"] = not has_blocker and not has_error

        summary = " | ".join(f"{r.layer.value}:{r.severity.value}" for r in results)
        state.setdefault("trace", []).append(f"[Step5 五层校验] {summary}")
        return state

    return validate_node
