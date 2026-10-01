"""
核心数据契约（Data Contract）。

所有跨模块/跨服务传递的数据都用 Pydantic 模型定义，好处：
- 类型安全、自动校验、自动生成 OpenAPI 文档（FastAPI 直接用）；
- 充当各层之间的"防腐层"，上下游解耦。
"""
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


# ============ Text-to-SQL ============

class ValidationLayer(str, Enum):
    """五层自校验的层级标识（对应方案 5.3.2 多层自校验引擎）。"""
    SYNTAX = "syntax"            # 1. 语法校验：能否被 SQL 解析器解析
    SCHEMA = "schema"           # 2. Schema 校验：表/列是否存在
    SECURITY = "security"       # 3. 安全校验：只读、禁危险操作、强制 LIMIT
    SEMANTIC = "semantic"       # 4. 语义校验：SQL 是否真的回答了用户问题（LLM 判定）
    PERFORMANCE = "performance"  # 5. 性能校验：全表扫描 / 缺分区裁剪等风险


class ValidationSeverity(str, Enum):
    PASS = "PASS"               # 通过
    WARN = "WARN"               # 警告（不阻断，记录风险）
    ERROR = "ERROR"            # 错误（可重试修正）
    BLOCKER = "BLOCKER"        # 阻断（直接拒绝，如出现 DROP/DELETE）


class ValidationResult(BaseModel):
    layer: ValidationLayer
    severity: ValidationSeverity
    message: str
    detail: str | None = None


class QueryRequest(BaseModel):
    question: str = Field(..., description="自然语言查询，例如：最近7天每天的订单量和支付金额")
    session_id: str = Field(default="default", description="会话 ID，用于多轮上下文")


class QueryResult(BaseModel):
    success: bool
    question: str
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    answer: str | None = None                      # 自然语言总结
    validations: list[ValidationResult] = Field(default_factory=list)
    retry_count: int = 0
    error: str | None = None
    trace: list[str] = Field(default_factory=list)  # 执行链路（每个节点的轨迹），便于调试与教学


# ============ 数据质量（DQ）============

class DQRuleType(str, Enum):
    NOT_NULL = "not_null"       # 非空
    UNIQUE = "unique"           # 唯一
    RANGE = "range"             # 区间
    STATISTICAL = "statistical"  # 统计异常（z_score / iqr / prophet）


class DQRule(BaseModel):
    id: str
    name: str
    table: str
    column: str
    type: DQRuleType
    params: dict[str, Any] = Field(default_factory=dict)
    severity: str = "P1"        # P0 最高
    schedule: str = "daily"


class DQCheckResult(BaseModel):
    rule_id: str
    passed: bool
    actual_value: Any | None = None
    checked_rows: int = 0
    details: list[Any] = Field(default_factory=list)  # 异常样本
    error: str | None = None
    message: str = ""


class AnomalyResult(BaseModel):
    is_anomaly: bool
    score: float = 0.0
    method: str = ""
    details: str = ""
    predicted_value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
