-- =====================================================================
-- ETL 加工与调优（离线数仓核心逻辑示例）
-- 说明：以下是各层之间加工的核心 SQL 片段 + 常见调优手段。
-- =====================================================================

-- -------------------------------
-- 1) ODS -> DWD 加工：增量去重 + 维度关联
-- -------------------------------
-- 关键点：明细层按"业务主键 + update_time"去重，保证同一运单只保留最新一条，
--       避免增量重跑导致数据翻倍。
INSERT OVERWRITE TABLE dwd.dwd_waybill_detail PARTITION (dt = '${dt}')
SELECT
    w.waybill_no,
    w.customer_id,
    w.origin_branch_id,
    w.dest_branch_id,
    ob.city AS origin_city,          -- 退化维度：把网点城市直接降到明细表
    db.city AS dest_city,
    w.cargo_type,
    w.weight,
    w.volume,
    w.waybill_status,
    w.create_time,
    w.update_time
FROM (
    SELECT *,
           row_number() OVER (
               PARTITION BY waybill_no
               ORDER BY update_time DESC
           ) AS rn
    FROM ods.ods_waybill_inc
    WHERE dt = '${dt}'
) w
LEFT JOIN dim.dim_branch ob ON w.origin_branch_id = ob.branch_id
LEFT JOIN dim.dim_branch db ON w.dest_branch_id = db.branch_id
WHERE w.rn = 1;

-- -------------------------------
-- 2) DIM 拉链表更新（SCD2）：客户状态变化时"关旧链、开新链"
-- -------------------------------
-- 将当天有变化的客户旧版本 end_date 置为昨天，新版本 start_date 置为今天。
INSERT OVERWRITE TABLE dim.dim_customer
SELECT
    customer_id, customer_name, customer_type, province, city, vip_level,
    start_date,
    CASE WHEN end_date = '9999-12-31' AND is_changed = 1
         THEN '${yesterday}' ELSE end_date END AS end_date
FROM (
    SELECT
        c.*,
        CASE WHEN o.customer_id IS NOT NULL THEN 1 ELSE 0 END AS is_changed
    FROM dim.dim_customer c
    LEFT JOIN (
        SELECT DISTINCT customer_id FROM ods.ods_customer_inc WHERE dt = '${dt}'
    ) o ON c.customer_id = o.customer_id
) t
UNION ALL
SELECT customer_id, customer_name, customer_type, province, city, vip_level,
       '${dt}' AS start_date, '9999-12-31' AS end_date
FROM ods.ods_customer_inc
WHERE dt = '${dt}';

-- -------------------------------
-- 3) DWD -> DWS 加工：日汇总聚合
-- -------------------------------
INSERT OVERWRITE TABLE dws.dws_transport_day_agg PARTITION (dt = '${dt}')
SELECT
    origin_branch_id,
    dest_branch_id,
    count(*)                AS transport_cnt,
    count(DISTINCT waybill_no) AS waybill_cnt,
    sum(mileage)            AS total_mileage,
    avg(transport_hours)    AS avg_transport_hours
FROM dwd.dwd_transport_detail
WHERE dt = '${dt}'
GROUP BY origin_branch_id, dest_branch_id;

-- -------------------------------
-- 4) 数据倾斜治理：随机前缀打散 + 二次聚合
-- -------------------------------
-- 问题：某个网点运单量极大 -> 单 Reduce 处理过慢。
-- 解法：第一步给 key 加随机前缀打散。第二步去掉前缀做真正聚合。
WITH salted AS (
    SELECT
        concat_ws('~', cast(floor(rand() * 100) AS int), branch_id) AS salted_key,
        waybill_no
    FROM dwd.dwd_delivery_detail
    WHERE dt = '${dt}'
),
first_agg AS (
    SELECT salted_key, count(1) AS cnt FROM salted GROUP BY salted_key
),
final_agg AS (
    SELECT split(salted_key, '~')[1] AS branch_id, sum(cnt) AS total_cnt
    FROM first_agg GROUP BY split(salted_key, '~')[1]
)
INSERT OVERWRITE TABLE dws.dws_delivery_day_agg PARTITION (dt = '${dt}')
SELECT branch_id, total_cnt FROM final_agg;

-- -------------------------------
-- 5) 其他常用调优
-- -------------------------------
-- 小文件合并：明细导入后文件过多，写 ADS 前用 coalesce 收敛分区内文件数
--   set spark.sql.shuffle.partitions=50;
--   ... SELECT /*+ COALESCE(10) */ ...  （Spark 3.x hint）

-- Map Join：小表（维度表）用 Broadcast 避免 shuffle
--   set hive.auto.convert.join=true;
--   SELECT /*+ MAPJOIN(db) */ ... FROM dwd_waybill_detail w JOIN dim_branch db ...

-- 分区裁剪：查询带 dt 分区条件，避免全表扫描
--   WHERE dt BETWEEN '2026-05-01' AND '2026-05-31'