"""
端到端冒烟测试：验证 Text-to-SQL Agent 与数据质量 Agent 的核心行为。

运行：
    python -m scripts.init_db   # 先建库
    pytest -q
"""
import os
import sqlite3

import pytest

from src.agents.orchestrator import get_orchestrator
from src.agents.data_quality.rule_engine import DQRuleEngine
from src.agents.data_quality.anomaly_detector import StatisticalAnomalyDetector
from src.schemas.models import DQRule, DQRuleType
from src.config import get_settings


@pytest.fixture(scope="module")
def orch():
    return get_orchestrator()


def _has_db():
    return os.path.exists(get_settings().sqlite_path)


# ---------------- Text-to-SQL ----------------
@pytest.mark.skipif(not _has_db(), reason="需先运行 python -m scripts.init_db")
def test_normal_query_executes(orch):
    """正常问题应成功生成并执行 SELECT。"""
    r = orch.run_text_to_sql("最近7天每天的订单量和支付金额")
    assert r.success is True
    assert r.sql.lower().startswith("select")
    assert r.row_count > 0


@pytest.mark.skipif(not _has_db(), reason="需先运行 python -m scripts.init_db")
def test_join_query(orch):
    """涉及商品的问题应生成 JOIN。"""
    r = orch.run_text_to_sql("销售额最高的前5个商品")
    assert r.success is True
    assert "join" in r.sql.lower()


@pytest.mark.skipif(not _has_db(), reason="需先运行 python -m scripts.init_db")
def test_dangerous_query_blocked(orch):
    """删除类问题应被安全层 BLOCKER 拦截，不执行。"""
    r = orch.run_text_to_sql("删除订单明细表所有数据")
    assert r.success is False
    assert "安全" in r.error or "DELETE" in r.error.upper()


@pytest.mark.skipif(not _has_db(), reason="需先运行 python -m scripts.init_db")
def test_hallucinated_column_exhausts_retry(orch):
    """引用不存在字段应触发 Schema ERROR，重试耗尽后失败。"""
    r = orch.run_text_to_sql("查一下每天的利润金额")
    assert r.success is False
    assert r.retry_count == get_settings().sql_max_retry


# ---------------- 数据质量 ----------------
@pytest.mark.skipif(not _has_db(), reason="需先运行 python -m scripts.init_db")
def test_dq_range_rule_catches_negative():
    """范围规则应抓到埋入的负金额订单。"""
    engine = DQRuleEngine()
    rule = DQRule(
        id="T_RANGE", name="金额范围", table="dwd_trade_order_detail",
        column="pay_amt", type=DQRuleType.RANGE, params={"min": 0, "max": 100000},
    )
    res = engine.run_check(rule)
    assert res.passed is False  # 存在 pay_amt=-100 的脏数据


def test_zscore_detects_spike():
    """Z-Score 应把明显尖刺判为异常。"""
    det = StatisticalAnomalyDetector()
    history = [10, 11, 12, 9, 10, 11, 13, 10, 12, 11]
    res = det.detect_zscore(current=60.0, history=history, threshold=3.0)
    assert res.is_anomaly is True


def test_iqr_is_robust():
    """IQR 对正常值不误报。"""
    det = StatisticalAnomalyDetector()
    history = [10, 11, 12, 9, 10, 11, 13, 10, 12, 11]
    res = det.detect_iqr(current=11.0, history=history)
    assert res.is_anomaly is False
