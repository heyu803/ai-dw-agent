-- =====================================================================
-- DWD 层：明细事实层
-- 定位：以业务过程为粒度生成"明细事实表"，维度描述尽量下沉为退化维度，
--       减少明细层与维度层的大表 Join。一行 = 一个业务事件的最细粒度。
-- =====================================================================

CREATE DATABASE IF NOT EXISTS dwd;

-- 1) 运单明细事实表（一行 = 一个运单，含退化维度字段）
CREATE TABLE IF NOT EXISTS dwd.dwd_waybill_detail (
    waybill_no       STRING COMMENT '运单号',
    customer_id      STRING COMMENT '客户ID（关联 dim_customer）',
    origin_branch_id STRING COMMENT '始发网点ID（关联 dim_branch）',
    dest_branch_id   STRING COMMENT '到达网点ID（关联 dim_branch）',
    origin_city      STRING COMMENT '始发城市（退化维度）',
    dest_city        STRING COMMENT '到达城市（退化维度）',
    cargo_type       STRING COMMENT '货物类型（退化维度）',
    weight           DOUBLE COMMENT '重量(kg)',
    volume           DOUBLE COMMENT '体积(m3)',
    waybill_status   STRING COMMENT '状态',
    create_time      STRING COMMENT '创建时间',
    update_time      STRING COMMENT '最后更新时间'
)
COMMENT '运单明细事实表（最细粒度：单个运单）'
PARTITIONED BY (dt STRING)
STORED AS PARQUET;

-- 2) 运输明细事实表（一行 = 一次运输批次）
CREATE TABLE IF NOT EXISTS dwd.dwd_transport_detail (
    transport_no     STRING COMMENT '运输批次号',
    waybill_no       STRING COMMENT '运单号',
    vehicle_id       STRING COMMENT '车辆ID',
    driver_id        STRING COMMENT '司机ID',
    origin_branch_id STRING COMMENT '发出网点ID',
    dest_branch_id   STRING COMMENT '到达网点ID',
    depart_time      STRING COMMENT '发车时间',
    arrive_time      STRING COMMENT '到达时间',
    mileage          DOUBLE COMMENT '里程(km)',
    transport_hours  DOUBLE COMMENT '运输时长(小时)'
)
COMMENT '运输明细事实表'
PARTITIONED BY (dt STRING)
STORED AS PARQUET;

-- 3) 派送明细事实表（一行 = 一次派送/签收）
CREATE TABLE IF NOT EXISTS dwd.dwd_delivery_detail (
    delivery_no  STRING COMMENT '派单号',
    waybill_no   STRING COMMENT '运单号',
    branch_id    STRING COMMENT '派送网点ID',
    courier_id   STRING COMMENT '快递员ID',
    sign_way     STRING COMMENT '签收方式',
    is_sign      STRING COMMENT '是否签收 Y/N',
    sign_time    STRING COMMENT '签收时间'
)
COMMENT '派送明细事实表'
PARTITIONED BY (dt STRING)
STORED AS PARQUET;