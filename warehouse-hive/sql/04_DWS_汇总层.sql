-- =====================================================================
-- DWS 层：汇总事实层
-- 定位：对 DWD 明细明细按主题、按时间粒度（日/周/月）预聚合，
--       面向分析场景"以空间换时间"，避免每次查询都扫描明细层。
-- =====================================================================

CREATE DATABASE IF NOT EXISTS dws;

-- 1) 运输主题-日汇总表（按运输发生日聚合）
CREATE TABLE IF NOT EXISTS dws.dws_transport_day_agg (
    dt               STRING COMMENT '发车日期分区',
    origin_branch_id STRING COMMENT '发出网点ID',
    dest_branch_id   STRING COMMENT '到达网点ID',
    transport_cnt    BIGINT COMMENT '运输批次量',
    waybill_cnt      BIGINT COMMENT '承运运单量',
    total_mileage    DOUBLE COMMENT '总里程(km)',
    avg_transport_hours DOUBLE COMMENT '平均运输时长(小时)'
)
COMMENT '运输主题-日汇总表'
PARTITIONED BY (dt STRING)
STORED AS PARQUET;

-- 2) 派送主题-日汇总表（按派送/签收日聚合）
CREATE TABLE IF NOT EXISTS dws.dws_delivery_day_agg (
    dt           STRING COMMENT '派送日期分区',
    branch_id    STRING COMMENT '派送网点ID',
    delivery_cnt BIGINT COMMENT '派送单量',
    signed_cnt   BIGINT COMMENT '签收单量',
    signed_rate  DOUBLE COMMENT '签收率'
)
COMMENT '派送主题-日汇总表'
PARTITIONED BY (dt STRING)
STORED AS PARQUET;

-- 3) 客户主题-运单汇总表（按客户聚合，支撑客户分析/分层）
CREATE TABLE IF NOT EXISTS dws.dws_customer_waybill_agg (
    customer_id   STRING COMMENT '客户ID',
    waybill_cnt   BIGINT COMMENT '累计运单量',
    total_weight  DOUBLE COMMENT '累计重量(kg)',
    total_volume  DOUBLE COMMENT '累计体积(m3)',
    last_day      STRING COMMENT '最近下单日期'
)
COMMENT '客户主题-运单累计汇总表'
STORED AS PARQUET;