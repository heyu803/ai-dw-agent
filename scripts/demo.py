"""
端到端演示：一条命令跑通 Text-to-SQL Agent + 数据质量 Agent 全链路。

运行：
    python -m scripts.init_db    # 先建数仓（只需一次）
    python -m scripts.demo       # 跑演示

默认 LLM_PROVIDER=mock，无需任何 API Key 即可看到完整链路。
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.orchestrator import get_orchestrator                       # noqa: E402
from src.agents.data_quality.rule_engine import DQRuleEngine               # noqa: E402
from src.agents.data_quality.anomaly_detector import StatisticalAnomalyDetector  # noqa: E402
from src.agents.data_quality.root_cause import RootCauseAnalyzer, AnomalyEvent   # noqa: E402
from src.schemas.models import DQRule, DQRuleType                          # noqa: E402
from src.config import get_settings                                        # noqa: E402

import sqlite3
from datetime import date


def hr(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def demo_text_to_sql():
    hr("一、Text-to-SQL Agent 演示（含 RAG / Schema Linking / 五层校验 / 沙箱）")
    orch = get_orchestrator()

    questions = [
        "最近7天每天的订单量和支付金额",        # 正常查询
        "销售额最高的前5个商品",                # 多表 JOIN
        "各省份的订单总数",                     # 维度下钻
        "删除订单明细表所有数据",               # 触发安全 BLOCKER
        "查一下每天的利润金额",                 # 触发 Schema 校验（不存在的列 profit_amt）
    ]

    for q in questions:
        print(f"\n🟦 问题：{q}")
        result = orch.run_text_to_sql(q)
        print("   链路轨迹：")
        for step in result.trace:
            print(f"     {step}")
        if result.success:
            print(f"   ✅ SQL: {result.sql}")
            print(f"   ✅ 结果: {result.row_count} 行，列={result.columns}")
            print(f"      前几行: {result.rows[:3]}")
            print(f"   💬 总结: {result.answer}")
        else:
            print(f"   ⛔ 未执行：{result.error}")
        # 打印校验明细
        if result.validations:
            print("   五层校验：")
            for v in result.validations:
                print(f"     - [{v.layer.value:11s}] {v.severity.value:7s} {v.message}")


def demo_data_quality():
    hr("二、数据质量 Agent 演示（规则检测 / 统计异常 / 根因分析）")
    engine = DQRuleEngine()
    today = date.today().isoformat()

    # ---- 规则型检测 ----
    print("\n【7.1 规则型检测引擎】")
    rules = [
        DQRule(id="R001", name="订单金额非空检查", table="dwd_trade_order_detail",
               column="pay_amt", type=DQRuleType.NOT_NULL, severity="P0"),
        DQRule(id="R002", name="用户ID非空检查", table="dwd_trade_order_detail",
               column="user_id", type=DQRuleType.NOT_NULL, severity="P0"),
        DQRule(id="R003", name="订单金额范围检查(0~100000)", table="dwd_trade_order_detail",
               column="pay_amt", type=DQRuleType.RANGE, params={"min": 0, "max": 100000}, severity="P1"),
    ]
    for r in rules:
        res = engine.run_check(r)
        flag = "✅ 通过" if res.passed else "❌ 失败"
        print(f"  {flag} [{r.id}] {res.message}")
        if res.details:
            print(f"        异常样本: {res.details[:2]}")

    # ---- 统计异常检测 ----
    print("\n【7.2 统计异常检测引擎】")
    s = get_settings()
    conn = sqlite3.connect(f"file:{s.sqlite_path}?mode=ro", uri=True)
    rows = conn.execute("SELECT dt, order_cnt FROM dws_trade_order_di ORDER BY dt").fetchall()
    conn.close()
    series = [r[1] for r in rows]
    history, current = series[:-1], series[-1]
    # 取那个尖刺日做演示（第 5 天前那条 order_cnt=60）
    spike = max(series)
    detector = StatisticalAnomalyDetector()
    z = detector.detect_zscore(float(spike), [float(x) for x in series if x != spike])
    iqr = detector.detect_iqr(float(spike), [float(x) for x in series if x != spike])
    print(f"  对尖刺值 order_cnt={spike} 做检测：")
    print(f"    z_score : is_anomaly={z.is_anomaly}, {z.details}")
    print(f"    iqr     : is_anomaly={iqr.is_anomaly}, {iqr.details}")

    # ---- 根因分析 ----
    print("\n【7.3 根因分析推理链（血缘追溯）】")
    analyzer = RootCauseAnalyzer(engine)
    report = analyzer.analyze(AnomalyEvent(table_name="dws_trade_order_di", dt=today, metric="order_cnt"))
    print(f"  异常表: {report.anomaly_table}")
    print(f"  上游血缘链: {report.upstream_chain}")
    for st in report.upstream_status:
        print(f"    - {st['table']}: {st['status']}  ({st['details']})")
    print(f"  🔎 根因结论: {report.conclusion}")


if __name__ == "__main__":
    if not os.path.exists(get_settings().sqlite_path):
        print("⚠️  未找到示例数仓，请先运行：python -m scripts.init_db")
        sys.exit(1)
    demo_text_to_sql()
    demo_data_quality()
    print("\n🎉 全部演示完成。建议对照 docs/ 下的说明书逐模块理解。")
