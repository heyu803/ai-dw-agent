-- =====================================================================
-- ODS 层：贴源层（物流域）
-- 定位：与业务系统表结构基本一致，只做最低限度的字段规范化 + 按日分区，
--       不做过多的清洗与维度关联，保证"原样落地、可回溯"。
-- 同步方式：DataX / 增量抽取，T+1 更新。
-- =====================================================================

CREATE DATABASE IF NOT EXISTS ods;

-- 1) 运单主表（货源系统的核心业务表）
CREATE TABLE IF NOT EXISTS ods.ods_waybill_inc (
    waybill_no       STRING COMMENT '运单号',
    customer_id      STRING COMMENT '寄件客户ID',
    origin_branch_id STRING COMMENT '始发网点ID',
    dest_branch_id   STRING COMMENT '到达网点ID',
    cargo_type       STRING COMMENT '货物类型',
    weight           DOUBLE COMMENT '重量(kg)',
    volume           DOUBLE COMMENT '体积(m3)',
    waybill_status   STRING COMMENT '状态：已揽收/运输中/已派送/已签收',
    create_time      STRING COMMENT '创建时间',
    update_time      STRING COMMENT '最后更新时间'
)
COMMENT '物流运单贴源表'
PARTITIONED BY (dt STRING COMMENT '日期分区 yyyy-MM-dd')
STORED AS PARQUET;

-- 2) 运输记录表（干线/支线运输过程）
CREATE TABLE IF NOT EXISTS ods.ods_transport_inc (
    transport_no     STRING COMMENT '运输批次号',
    waybill_no       STRING COMMENT '关联运单号',
    vehicle_id       STRING COMMENT '车辆ID',
    driver_id        STRING COMMENT '司机ID',
    origin_branch_id STRING COMMENT '发出网点ID',
    dest_branch_id   STRING COMMENT '到达网点ID',
    depart_time      STRING COMMENT '发车时间',
    arrive_time      STRING COMMENT '到达时间',
    mileage          DOUBLE COMMENT '里程(km)',
    update_time      STRING COMMENT '最后更新时间'
)
COMMENT '物流运输记录贴源表'
PARTITIONED BY (dt STRING)
STORED AS PARQUET;

-- 3) 派送记录表（末端派送/签收）
CREATE TABLE IF NOT EXISTS ods.ods_delivery_inc (
    delivery_no      STRING COMMENT '派单号',
    waybill_no       STRING COMMENT '关联运单号',
    branch_id        STRING COMMENT '派送网点ID',
    courier_id       STRING COMMENT '快递员ID',
    sign_way         STRING COMMENT '签收方式：本人签收/代收/驿站',
    is_sign          STRING COMMENT '是否签收：Y/N',
    sign_time        STRING COMMENT '签收时间',
    update_time      STRING COMMENT '最后更新时间'
)
COMMENT '物流派送记录贴源表'
PARTITIONED BY (dt STRING)
STORED AS PARQUET;

-- 4) 客户主表
CREATE TABLE IF NOT EXISTS ods.ods_customer_inc (
    customer_id   STRING COMMENT '客户ID',
    customer_name STRING COMMENT '客户名称',
    customer_type STRING COMMENT '客户类型：个人/企业',
    province      STRING COMMENT '所在省份',
    city          STRING COMMENT '所在城市',
    vip_level     STRING COMMENT '会员等级',
    status        STRING COMMENT '状态：1正常/0注销',
    update_time   STRING COMMENT '最后更新时间'
)
COMMENT '物流客户贴源表'
PARTITIONED BY (dt STRING)
STORED AS PARQUET;

-- 5) 网点主表
CREATE TABLE IF NOT EXISTS ods.ods_branch_inc (
    branch_id    STRING COMMENT '网点ID',
    branch_name  STRING COMMENT '网点名称',
    region       STRING COMMENT '所属大区',
    province     STRING COMMENT '省份',
    city         STRING COMMENT '城市',
    branch_level STRING COMMENT '网点级别：一级/二级/三级',
    update_time  STRING COMMENT '最后更新时间'
)
COMMENT '物流网点贴源表'
PARTITIONED BY (dt STRING)
STORED AS PARQUET;