-- =====================================================================
-- ADS 层：应用层
-- 定位：直接面向 BI 报表、看板与业务决策的应用指标表，
--       由 DWS / DWD 加工，落到 MySQL（或报表库）供可视化工具取数。
-- =====================================================================

CREATE DATABASE IF NOT EXISTS ads;

-- 1) 物流运营日报（管理层核心报表）
CREATE TABLE IF NOT EXISTS ads.ads_logistics_daily_report (
    dt             STRING COMMENT '日期分区',
    total_waybill  BIGINT COMMENT '当日总运单量',
    total_transport BIGINT COMMENT '当日运输批次量',
    total_delivery BIGINT COMMENT '当日派送单量',
    signed_cnt     BIGINT COMMENT '当日签收单量',
    signed_rate    DOUBLE COMMENT '整体签收率',
    total_mileage  DOUBLE COMMENT '当日总里程(km)'
)
COMMENT '物流运营日报（应用指标）'
PARTITIONED BY (dt STRING)
STORED AS PARQUET;

-- 2) 网点 KPI 表（考核各网点经营质量）
CREATE TABLE IF NOT EXISTS ads.ads_branch_kpi (
    dt            STRING COMMENT '日期分区',
    branch_id     STRING COMMENT '网点ID',
    receipt_cnt   BIGINT COMMENT '揽收单量',
    delivery_cnt  BIGINT COMMENT '派送单量',
    signed_rate   DOUBLE COMMENT '签收率',
    avg_mileage   DOUBLE COMMENT '平均里程(km)'
)
COMMENT '网点 KPI 指标表'
PARTITIONED BY (dt STRING)
STORED AS PARQUET;