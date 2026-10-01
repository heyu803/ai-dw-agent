# 七、数据质量治理 Agent

> 对应原方案第七章（图5）。数据质量（DQ）Agent 是数仓提效的另一半：不只是"取数快"，还要"数据对"。包含三件套：规则检测、统计异常检测、根因分析。

## 7.1 规则型检测引擎（DQRuleEngine）

最基础的数据质量保障：用**可配置的规则**周期性扫描表，发现违规数据。

本项目 `src/agents/data_quality/rule_engine.py` 实现了三类规则模板（对应原文档代码）：

| 规则类型 | 含义 | 检测 SQL 思路 |
|---|---|---|
| `not_null` | 某列不能为空 | `COUNT(*) WHERE column IS NULL` == 0 才通过 |
| `unique` | 某列唯一 | `COUNT(*) - COUNT(DISTINCT column)` == 0 才通过 |
| `range` | 某列在合理范围 | `COUNT(*) WHERE column NOT BETWEEN min AND max` == 0 才通过 |

规则用类似 YAML 的配置描述（对应原文档"规则配置示例"）：

```yaml
rules:
  - id: "R001"
    name: "订单金额非空检查"
    table: "dws_trade_order_di"
    column: "pay_amt"
    type: "not_null"
    severity: "P0"
    schedule: "daily"
  - id: "R002"
    name: "订单金额范围检查"
    table: "dws_trade_order_di"
    column: "pay_amt"
    type: "range"
    params: {min: 0, max: 1000000}
    severity: "P1"
```

`run_check()` 根据规则类型生成检测 SQL，执行后**违规行数 == 0 即通过**，并保留异常样本（`details`）便于排查。

> demo 里 `init_db.py` 故意埋了一条 `pay_amt=-100` 的负金额订单和一条 `user_id=NULL` 的订单，所以跑 demo 时会看到 range 规则和 not_null 规则失败，并打印出具体的异常样本行。

## 7.2 统计异常检测引擎（StatisticalAnomalyDetector）

规则检测能抓"硬错误"（空值、越界），但抓不住"软异常"——比如某天订单量突然暴涨/暴跌但仍在合法范围内。这就需要**统计方法**。

`src/agents/data_quality/anomaly_detector.py` 实现三种方法：

### ① Z-Score（标准分数）
```
z = |current - mean| / std
z > threshold(默认3.0) 即判为异常
```
适用于近似正态分布的数据。**缺点**：对极端值敏感（一个离群点会拉高 std/mean）。

### ② IQR（四分位距）
```
Q1 = 25 分位, Q3 = 75 分位, IQR = Q3 - Q1
正常范围 = [Q1 - factor*IQR, Q3 + factor*IQR]（factor 默认 1.5）
落在范围外即异常
```
**优点**：基于分位数，**对极端值不敏感**，比 Z-Score 更鲁棒。

### ③ Prophet（趋势预测）
对有**周期性/季节性**的时间序列（如每日订单量有周末效应），用 Prophet 拟合趋势+季节性，预测出当日的合理区间 `[yhat_lower, yhat_upper]`，实际值落在区间外即异常。本项目中 Prophet 为可选依赖，未安装时该方法自动降级（不影响前两种）。

> **面试点**：被问"怎么做异常检测"——能分场景回答最佳：分布近似正态用 Z-Score；有离群点干扰用 IQR（更鲁棒）；有明显周期性用 Prophet/时序模型。再往上还有 STL 分解、孤立森林（Isolation Forest）等。

demo 里对埋入的"尖刺值 order_cnt=60"做检测，Z-Score 和 IQR 都会判定为异常（Z-Score≈20，远超阈值 3）。

## 7.3 根因分析推理链（RootCauseAnalyzer）

发现异常只是第一步，**定位根因**才是价值所在。`src/agents/data_quality/root_cause.py` 实现"多步推理：异常 → 血缘追溯 → 变更排查 → 根因排序"。

核心思路：数仓的表有**血缘关系**（下游表由上游表加工而来）。当下游表 `dws_trade_order_di` 出现异常时，沿着血缘链往上游追溯，**逐个检查上游表的数据质量**：
- 如果某个上游表也异常 → 根因很可能在上游（问题向上传导）；
- 如果所有上游都正常 → 异常可能源于本表自身的 ETL 逻辑或当日业务真实波动。

```
Step 1: 获取上游血缘链（生产用 Neo4j Cypher：get_upstream_chain，本项目用内置 LINEAGE 字典 BFS）
Step 2: 对每个上游表跑一遍 DQ 规则快速探针（quick_check）
Step 3: 汇总每个上游的 normal/abnormal 状态
Step 4: 根据"哪些环节异常"推断并排序根因，给出结论与人工复核建议
```

- 血缘存储：生产用 **Neo4j 图数据库**（`MATCH` 上游链查询性能优）；本项目用内置 `LINEAGE` 字典 + BFS 模拟，`get_upstream_chain()` 接口与生产一致，便于替换。

> **面试点**：根因分析的精髓是"**结合血缘做因果推断**"，而不是孤立地看单表。能讲出"异常会沿血缘向下游传导，所以要溯源到最上游的异常点"就抓住了核心。

## 关键文件索引

- `src/agents/data_quality/rule_engine.py`：规则引擎（not_null / unique / range）
- `src/agents/data_quality/anomaly_detector.py`：统计异常（Z-Score / IQR / Prophet）
- `src/agents/data_quality/root_cause.py`：根因分析（血缘追溯 + 多步推理）
- 对外 API：`src/api/dq.py`（`/api/v1/dq/check`、`/api/v1/dq/root-cause`）
