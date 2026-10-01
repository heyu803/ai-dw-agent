"""
根因分析推理链（对应方案 7.3 根因分析推理链 / 图5 RootCauseAnalyzer）。

多步推理：异常 → 血缘追溯（上游表）→ 逐个排查上游数据质量 → 根因排序。
这是 DQ Agent 区别于"传统监控告警"的关键：不只是报警，还自动定位"为什么坏了"。

文档里上游血缘来自 Neo4j（neo4j_client.get_upstream_chain）。这里用一份
内置的血缘字典替代（生产从 Neo4j 血缘图谱实时查询），其余逻辑保持一致。
"""
from dataclasses import dataclass, field
from .rule_engine import DQRuleEngine
from ...schemas.models import DQRule, DQRuleType


# 内置血缘：下游表 -> 上游表列表（生产从 Neo4j 查询）
LINEAGE = {
    "dws_trade_order_di": ["dwd_trade_order_detail"],
    "dwd_trade_order_detail": ["dim_user", "dim_product", "dim_shop"],
}


@dataclass
class AnomalyEvent:
    table_name: str
    dt: str
    metric: str
    description: str = ""


@dataclass
class RootCauseReport:
    anomaly_table: str
    upstream_chain: list[str] = field(default_factory=list)
    upstream_status: list[dict] = field(default_factory=list)
    root_causes: list[str] = field(default_factory=list)
    conclusion: str = ""


class RootCauseAnalyzer:
    """数据质量异常根因分析。"""

    def __init__(self, dq_engine: DQRuleEngine | None = None):
        self.dq_engine = dq_engine or DQRuleEngine()

    def get_upstream_chain(self, table: str, max_depth: int = 3) -> list[str]:
        """递归获取上游血缘链（BFS，去重）。"""
        chain, frontier, depth = [], [table], 0
        seen = {table}
        while frontier and depth < max_depth:
            nxt = []
            for t in frontier:
                for up in LINEAGE.get(t, []):
                    if up not in seen:
                        seen.add(up)
                        chain.append(up)
                        nxt.append(up)
            frontier, depth = nxt, depth + 1
        return chain

    def analyze(self, anomaly: AnomalyEvent) -> RootCauseReport:
        """多步推理：异常 → 血缘追溯 → 变更排查 → 根因排序。"""
        report = RootCauseReport(anomaly_table=anomaly.table_name)

        # Step1: 获取上游血缘链
        lineage = self.get_upstream_chain(anomaly.table_name, max_depth=3)
        report.upstream_chain = lineage

        # Step2: 逐个检查上游表数据质量（用一条 not_null 探针规则做快速体检）
        for table in lineage:
            probe = DQRule(
                id=f"probe_{table}", name=f"{table} 主键非空探针",
                table=table, column=self._pk_of(table), type=DQRuleType.NOT_NULL,
                params={"dt": anomaly.dt} if table.startswith(("dwd", "dws")) else {},
            )
            result = self.dq_engine.run_check(probe)
            status = "abnormal" if not result.passed else "normal"
            report.upstream_status.append({
                "table": table, "status": status,
                "details": result.message,
            })
            if status == "abnormal":
                report.root_causes.append(f"上游表 {table} 数据异常：{result.message}")

        # Step3: 根因结论
        if report.root_causes:
            report.conclusion = (
                f"异常表 {anomaly.table_name} 的根因疑似来自上游："
                + "；".join(report.root_causes)
            )
        else:
            report.conclusion = (
                f"上游血缘 {lineage} 数据质量均正常，"
                f"异常可能源于 {anomaly.table_name} 自身的 ETL 逻辑或当日业务真实波动，建议人工复核。"
            )
        return report

    @staticmethod
    def _pk_of(table: str) -> str:
        return {
            "dim_user": "user_id", "dim_product": "product_id", "dim_shop": "shop_id",
            "dwd_trade_order_detail": "order_id", "dws_trade_order_di": "dt",
        }.get(table, "id")
