# 离线数仓分层建模实践（物流域 · Hive/Spark SQL）

> 本目录是「AI 数仓 Agent」项目的**离线数仓部分**——以**物流业务**为例，演示
> ODS → DIM/DWD → DWS → ADS 五层分层建模的完整建表（DDL）与加工（ETL）逻辑。
>
> 技术栈：Hadoop（HDFS / MapReduce）+ Hive + Spark + DataX + DolphinScheduler，
> 与生产离线数仓一致。以下 SQL 为**建模参考脚本**，需部署在 Hadoop/Hive 环境执行，
> 存储格式为 Parquet + 按日分区。

## 五层定位

| 层 | 定位 | 文件 |
|---|---|---|
| ODS 贴源层 | 与业务系统基本一致，只做字段规范化与分区 | `sql/01_ODS_贴源层.sql` |
| DIM 维度层 | 统一维度口径，含缓慢变化维（拉链表） | `sql/02_DIM_维度层.sql` |
| DWD 明细层 | 维度退化，生成明细事实宽表 | `sql/03_DWD_明细层.sql` |
| DWS 汇总层 | 按日 / 客户等维度聚合指标 | `sql/04_DWS_汇总层.sql` |
| ADS 应用层 | 面向报表与看板的应用指标 | `sql/05_ADS_应用层.sql` |
| ETL 加工 | 层间加工逻辑与性能调优 | `sql/06_ETL_加工与调优.sql` |

## 建模要点（面试常问）

- **星型模型**：事实表只存维度外键 + 度量，查找属性下沉为退化维度，减少 Join。
- **缓慢变化维（SCD2 拉链表）**：`dim_customer` 用 `start_date / end_date` 记录客户状态变更，
  保留历史版本，避免直接覆盖。
- **分区与去重**：全表按 `dt` 日分区；增量同步用 `row_number() + max(update_time)` 去重，
  防止重复导入造成数据翻倍。
- **数据治理**：`sql/06` 演示数据倾斜处理（加盐打散 + 二次聚合）、小文件合并（`coalesce`）、
  Map Join 优化等常见离线数仓调优手段。