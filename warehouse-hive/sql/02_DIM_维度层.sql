-- =====================================================================
-- DIM 层：维度层
-- 定位：统一维度口径，是整个数仓"事实-维度"星型模型的公共支撑。
--       维度表由 ODS 层清洗、去重、标准化后生成。
-- =====================================================================

CREATE DATABASE IF NOT EXISTS dim;

-- 1) 日期维度表（最常用的公共维度，一般一次性生成若干年）
CREATE TABLE IF NOT EXISTS dim.dim_date (
    date_id     STRING COMMENT '日期，格式 yyyy-MM-dd（主键）',
    year        INT    COMMENT '年',
    quarter     INT    COMMENT '季度',
    month       INT    COMMENT '月',
    day         INT    COMMENT '日',
    week_of_year INT   COMMENT '年内第几周',
    is_weekend  STRING COMMENT '是否周末 Y/N',
    is_holiday  STRING COMMENT '是否节假日 Y/N'
)
COMMENT '日期维度表'
STORED AS PARQUET;

-- 2) 客户维度表（SCD2 拉链表：记录客户状态的历史变更，保留全历史）
CREATE TABLE IF NOT EXISTS dim.dim_customer (
    customer_id   STRING COMMENT '客户ID（业务主键）',
    customer_name STRING COMMENT '客户名称',
    customer_type STRING COMMENT '客户类型：个人/企业',
    province      STRING COMMENT '所在省份',
    city          STRING COMMENT '所在城市',
    vip_level     STRING COMMENT '会员等级',
    start_date    STRING COMMENT '该版本生效日期 yyyy-MM-dd',
    end_date      STRING COMMENT '该版本失效日期，9999-12-31 表示当前有效'
)
COMMENT '客户维度表（拉链表）'
STORED AS PARQUET;

-- 3) 网点维度表
CREATE TABLE IF NOT EXISTS dim.dim_branch (
    branch_id    STRING COMMENT '网点ID（主键）',
    branch_name  STRING COMMENT '网点名称',
    region       STRING COMMENT '所属大区',
    province     STRING COMMENT '省份',
    city         STRING COMMENT '城市',
    branch_level STRING COMMENT '网点级别'
)
COMMENT '网点维度表'
STORED AS PARQUET;

-- 4) 车辆维度表
CREATE TABLE IF NOT EXISTS dim.dim_vehicle (
    vehicle_id    STRING COMMENT '车辆ID（主键）',
    plate_no      STRING COMMENT '车牌号',
    vehicle_type  STRING COMMENT '车型：厢式/挂车/冷链',
    load_capacity DOUBLE COMMENT '载重(吨)',
    vehicle_status STRING COMMENT '状态：运营中/维修/报废'
)
COMMENT '车辆维度表'
STORED AS PARQUET;

-- 5) 司机维度表
CREATE TABLE IF NOT EXISTS dim.dim_driver (
    driver_id   STRING COMMENT '司机ID（主键）',
    driver_name STRING COMMENT '司机姓名',
    license_type STRING COMMENT '驾照类型',
    phone       STRING COMMENT '联系电话',
    entry_date  STRING COMMENT '入职日期'
)
COMMENT '司机维度表'
STORED AS PARQUET;