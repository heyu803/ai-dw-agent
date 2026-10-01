"""
示例电商数仓的 Schema 定义（单一数据源 Single Source of Truth）。

scripts/init_db.py 用它建 SQLite 表并灌入模拟数据；
RAG 知识库用它建索引。两者共用同一份定义，避免漂移。

数仓分层（数仓常识，面试常问）：
- dim_*  维度表：用户、商品、店铺
- dwd_*  明细事实表：订单明细（最细粒度）
- dws_*  汇总事实表：按天聚合的交易汇总（图5中出现的 dws_trade_order_di）
"""
from .rag.pipeline import TableSchema

TABLES: list[TableSchema] = [
    TableSchema(
        name="dws_trade_order_di",
        description="交易域-每日订单汇总表（按天聚合的核心指标，BI 大盘常用）",
        columns=[
            ("dt", "TEXT", "日期分区，格式 YYYY-MM-DD"),
            ("order_cnt", "INTEGER", "当日订单数"),
            ("pay_amt", "REAL", "当日支付总金额(元)"),
            ("user_cnt", "INTEGER", "当日下单用户数"),
        ],
    ),
    TableSchema(
        name="dwd_trade_order_detail",
        description="交易域-订单明细事实表（最细粒度，一行=一笔订单中的一个商品）",
        columns=[
            ("order_id", "TEXT", "订单ID"),
            ("dt", "TEXT", "下单日期分区"),
            ("user_id", "INTEGER", "用户ID，关联 dim_user"),
            ("product_id", "INTEGER", "商品ID，关联 dim_product"),
            ("shop_id", "INTEGER", "店铺ID，关联 dim_shop"),
            ("pay_amt", "REAL", "该商品支付金额(元)"),
            ("quantity", "INTEGER", "购买数量"),
        ],
    ),
    TableSchema(
        name="dim_user",
        description="用户维度表（用户基础属性）",
        columns=[
            ("user_id", "INTEGER", "用户ID(主键)"),
            ("user_name", "TEXT", "用户名"),
            ("province", "TEXT", "所在省份"),
            ("gender", "TEXT", "性别 M/F"),
            ("reg_date", "TEXT", "注册日期"),
        ],
    ),
    TableSchema(
        name="dim_product",
        description="商品维度表（商品基础属性）",
        columns=[
            ("product_id", "INTEGER", "商品ID(主键)"),
            ("product_name", "TEXT", "商品名称"),
            ("category", "TEXT", "商品类目"),
            ("price", "REAL", "标准售价(元)"),
        ],
    ),
    TableSchema(
        name="dim_shop",
        description="店铺维度表（店铺基础属性）",
        columns=[
            ("shop_id", "INTEGER", "店铺ID(主键)"),
            ("shop_name", "TEXT", "店铺名称"),
            ("city", "TEXT", "店铺所在城市"),
        ],
    ),
]

TABLES_BY_NAME = {t.name: t for t in TABLES}
