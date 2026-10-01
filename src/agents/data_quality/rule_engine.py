"""
数据质量规则检测引擎（对应方案 7.1 规则型检测引擎 / 图5 DQRuleEngine）。

与文档一致的设计：
- run_check：执行单条规则，返回 DQCheckResult（含异常样本）；
- _build_check_sql：按规则类型用模板生成"违规计数 SQL"。

文档里用的是 presto_client（生产数仓引擎），这里改造为 SQLite 只读执行，
逻辑完全一致：违规行数 == 0 即通过。
"""
import sqlite3
from ...schemas.models import DQRule, DQCheckResult, DQRuleType
from ...config import get_settings


class DQRuleEngine:
    """数据质量规则检测引擎。"""

    # 各规则类型 -> "违规计数" SQL 模板（COUNT 出不满足规则的行数）
    TEMPLATES = {
        DQRuleType.NOT_NULL: "SELECT COUNT(*) FROM {table} WHERE {column} IS NULL{dt_clause}",
        DQRuleType.UNIQUE: "SELECT COUNT(*) - COUNT(DISTINCT {column}) FROM {table}{dt_where}",
        DQRuleType.RANGE: "SELECT COUNT(*) FROM {table} WHERE {column} NOT BETWEEN {min} AND {max}{dt_clause}",
    }

    def run_check(self, rule: DQRule) -> DQCheckResult:
        try:
            check_sql = self._build_check_sql(rule)
            sample_sql = self._build_sample_sql(rule)

            s = get_settings()
            conn = sqlite3.connect(f"file:{s.sqlite_path}?mode=ro", uri=True)
            cur = conn.cursor()

            cur.execute(check_sql)
            violation_cnt = cur.fetchone()[0]

            details = []
            if violation_cnt and sample_sql:
                cur.execute(sample_sql)
                details = [list(r) for r in cur.fetchall()]
            conn.close()

            passed = (violation_cnt == 0)
            return DQCheckResult(
                rule_id=rule.id,
                passed=passed,
                actual_value=violation_cnt,
                checked_rows=violation_cnt,
                details=details,                       # 保留异常样本（最多10条）
                message=(
                    f"规则[{rule.name}]通过" if passed
                    else f"规则[{rule.name}]失败：发现 {violation_cnt} 行违规"
                ),
            )
        except Exception as e:  # noqa: BLE001
            return DQCheckResult(rule_id=rule.id, passed=False, error=str(e),
                                 message=f"规则执行异常：{e}")

    # ------------------------------------------------------------------
    def _dt_clause(self, rule: DQRule, with_where: bool = False) -> tuple[str, str]:
        """根据是否指定 dt 生成过滤子句。"""
        dt = rule.params.get("dt")
        if not dt:
            return "", ""
        clause = f" AND dt = '{dt}'"           # 接在已有 WHERE 后面
        where = f" WHERE dt = '{dt}'"          # 独立 WHERE
        return clause, where

    def _build_check_sql(self, rule: DQRule) -> str:
        """根据规则类型生成检测 SQL（与文档 _build_check_sql 同构）。"""
        dt_clause, dt_where = self._dt_clause(rule)
        tpl = self.TEMPLATES[rule.type]
        return tpl.format(
            table=rule.table, column=rule.column,
            min=rule.params.get("min", 0), max=rule.params.get("max", 0),
            dt_clause=dt_clause, dt_where=dt_where,
        )

    def _build_sample_sql(self, rule: DQRule) -> str | None:
        """取违规样本（最多10条），便于排查。"""
        dt_clause, dt_where = self._dt_clause(rule)
        if rule.type == DQRuleType.NOT_NULL:
            return f"SELECT * FROM {rule.table} WHERE {rule.column} IS NULL{dt_clause} LIMIT 10"
        if rule.type == DQRuleType.RANGE:
            return (f"SELECT * FROM {rule.table} WHERE {rule.column} "
                    f"NOT BETWEEN {rule.params.get('min',0)} AND {rule.params.get('max',0)}{dt_clause} LIMIT 10")
        return None
