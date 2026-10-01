"""DQ Service —— 数据质量检测 API（对应应用服务层 BFF 的 DQ Service）。"""
from fastapi import APIRouter
from ..schemas.models import DQRule, DQCheckResult
from ..agents.data_quality.rule_engine import DQRuleEngine
from ..agents.data_quality.root_cause import RootCauseAnalyzer, AnomalyEvent

router = APIRouter(prefix="/api/v1/dq", tags=["Data Quality"])
_engine = DQRuleEngine()
_analyzer = RootCauseAnalyzer(_engine)


@router.post("/check", response_model=DQCheckResult, summary="执行单条数据质量规则")
def check(rule: DQRule) -> DQCheckResult:
    return _engine.run_check(rule)


@router.post("/root-cause", summary="对异常做根因分析（血缘追溯）")
def root_cause(table: str, dt: str, metric: str = "order_cnt"):
    report = _analyzer.analyze(AnomalyEvent(table_name=table, dt=dt, metric=metric))
    return {
        "anomaly_table": report.anomaly_table,
        "upstream_chain": report.upstream_chain,
        "upstream_status": report.upstream_status,
        "root_causes": report.root_causes,
        "conclusion": report.conclusion,
    }
