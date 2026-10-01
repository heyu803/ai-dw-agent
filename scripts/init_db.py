"""
初始化示例电商数仓（SQLite），开箱即用。

运行：python -m scripts.init_db
会在 data/warehouse.db 建表并灌入模拟数据，其中故意埋了几条异常数据，
用于演示数据质量 Agent 的检测与根因分析能力。
"""
import os
import sqlite3
import random
from datetime import date, timedelta

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.warehouse_schema import TABLES  # noqa: E402
from src.config import get_settings       # noqa: E402

random.seed(42)

PROVINCES = ["广东", "北京", "上海", "浙江", "江苏", "四川"]
CITIES = ["深圳", "北京", "上海", "杭州", "南京"]
CATEGORIES = ["手机数码", "服饰鞋包", "家居家电", "食品生鲜", "美妆护肤"]


def _create_tables(cur):
    type_map = {"TEXT": "TEXT", "INTEGER": "INTEGER", "REAL": "REAL"}
    for t in TABLES:
        cols = ", ".join(f"{c} {type_map[ty]}" for c, ty, _ in t.columns)
        cur.execute(f"DROP TABLE IF EXISTS {t.name}")
        cur.execute(f"CREATE TABLE {t.name} ({cols})")


def _seed(cur):
    # ---- dim_user ----
    users = []
    for uid in range(1, 21):
        users.append((uid, f"用户{uid}", random.choice(PROVINCES),
                      random.choice(["M", "F"]), "2024-01-01"))
    cur.executemany("INSERT INTO dim_user VALUES (?,?,?,?,?)", users)

    # ---- dim_product ----
    products = []
    for pid in range(1, 11):
        products.append((pid, f"商品{pid}", random.choice(CATEGORIES), round(random.uniform(50, 2000), 2)))
    cur.executemany("INSERT INTO dim_product VALUES (?,?,?,?)", products)

    # ---- dim_shop ----
    shops = [(sid, f"店铺{sid}", random.choice(CITIES)) for sid in range(1, 6)]
    cur.executemany("INSERT INTO dim_shop VALUES (?,?,?)", shops)

    # ---- 30 天明细 + 汇总 ----
    today = date.today()
    details, summary = [], []
    order_seq = 0
    for d in range(29, -1, -1):
        dt = (today - timedelta(days=d)).isoformat()
        # 当日订单数：基线 8~15；第 5 天前制造一个异常尖刺
        base = random.randint(8, 15)
        if d == 5:
            base = 60  # 异常尖刺，供统计异常检测命中
        day_users = set()
        day_amt = 0.0
        for _ in range(base):
            order_seq += 1
            uid = random.randint(1, 20)
            pid = random.randint(1, 10)
            sid = random.randint(1, 5)
            qty = random.randint(1, 3)
            amt = round(random.uniform(50, 1500), 2)
            details.append((f"O{order_seq:06d}", dt, uid, pid, sid, amt, qty))
            day_users.add(uid)
            day_amt += amt
        summary.append((dt, base, round(day_amt, 2), len(day_users)))

    # 埋点1：一条明细的 pay_amt 为负（触发 range 规则失败）
    details.append(("O999001", today.isoformat(), 3, 2, 1, -100.0, 1))
    # 埋点2：一条明细的 user_id 为 NULL（触发 not_null 规则失败 + 根因分析）
    details.append(("O999002", today.isoformat(), None, 5, 2, 200.0, 1))

    cur.executemany("INSERT INTO dwd_trade_order_detail VALUES (?,?,?,?,?,?,?)", details)
    cur.executemany("INSERT INTO dws_trade_order_di VALUES (?,?,?,?)", summary)


def main():
    s = get_settings()
    db_path = s.sqlite_path
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    _create_tables(cur)
    _seed(cur)
    conn.commit()

    # 打印概况
    print(f"✅ 示例数仓已生成: {db_path}")
    for t in TABLES:
        cur.execute(f"SELECT COUNT(*) FROM {t.name}")
        print(f"   - {t.name}: {cur.fetchone()[0]} 行")
    print("\n💡 已故意埋入异常数据：负金额订单、NULL 用户ID 订单、某日订单量尖刺，供 DQ Agent 演示。")
    conn.close()


if __name__ == "__main__":
    main()
