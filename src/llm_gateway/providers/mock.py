"""
Mock LLM Provider —— 离线、零依赖、可复现。

为什么需要它（面试可讲）：
- 让整条 Agent 链路在没有 API Key / 没有 GPU 的情况下也能端到端跑通，
  方便教学、CI 测试、本地调试；
- 真实环境只需把 LLM_PROVIDER 切成 openai_compatible 即可无缝替换。

它不是"真 LLM"，而是基于关键词 + 模板，针对示例电商数仓返回合理的 SQL / 语义判断。
覆盖了 demo 脚本里的几个典型问题；对未命中的问题会返回一个保守的探查 SQL。
"""
import re
import json
from .base import LLMProvider


class MockLLMProvider(LLMProvider):
    name = "mock"

    def complete(self, prompt: str, *, system: str = "", temperature: float = 0.0) -> str:
        p = prompt.lower()

        # ---- 语义校验场景：判断 SQL 是否回答了问题 ----
        if "判断下面的 sql 是否正确回答了用户问题" in prompt or "semantic check" in p:
            # mock 一律认为语义匹配（真实环境由 LLM 判断）
            return json.dumps({"match": True, "reason": "SQL 选取的指标与时间范围与问题一致"}, ensure_ascii=False)

        # ---- 自然语言总结场景 ----
        if "用一句话总结查询结果" in prompt or "summarize" in p:
            return self._summarize(prompt)

        # ---- SQL 生成场景（含修正重试）----
        return self._generate_sql(prompt)

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_question(prompt: str) -> str:
        """从 Prompt 中抽取【用户问题】部分，避免被 schema 文本里的词干扰匹配。

        注意：Prompt 模板的说明行里也会出现 “请根据【用户问题】和【可用表结构】…”，
        正则会匹配到这一处而误抽到“和”。因此这里取所有匹配中最长的一段，
        即真正承载问题内容的数据块。"""
        matches = re.findall(r"【用户问题】\s*(.*?)\s*【", prompt, re.DOTALL)
        if matches:
            return max(matches, key=len).strip()
        return prompt

    def _generate_sql(self, prompt: str) -> str:
        q = self._extract_question(prompt)  # 只看用户问题
        ql = q.lower()

        def wrap(sql: str) -> str:
            # 模拟 LLM 用 ```sql ``` 包裹输出，考验下游的解析鲁棒性
            return f"```sql\n{sql.strip()}\n```"

        # 问题1：最近7天每天的订单量和支付金额
        if ("7" in q or "七" in q) and ("订单" in q or "order" in ql):
            return wrap("""
SELECT dt, order_cnt, pay_amt
FROM dws_trade_order_di
ORDER BY dt DESC
LIMIT 7
""")

        # 问题2：销售额最高的5个商品
        if ("商品" in q or "product" in ql) and ("最高" in q or "top" in ql or "前" in q):
            return wrap("""
SELECT p.product_name, SUM(d.pay_amt) AS total_amt
FROM dwd_trade_order_detail d
JOIN dim_product p ON d.product_id = p.product_id
GROUP BY p.product_name
ORDER BY total_amt DESC
LIMIT 5
""")

        # 问题3：各省份的订单总数
        if "省" in q or "province" in ql or "地区" in q:
            return wrap("""
SELECT u.province, COUNT(*) AS order_cnt
FROM dwd_trade_order_detail d
JOIN dim_user u ON d.user_id = u.user_id
GROUP BY u.province
ORDER BY order_cnt DESC
""")

        # 问题4（演示安全校验拦截）：删除订单表 -> 故意生成危险 SQL
        if "删除" in q or "drop" in ql or "delete" in ql:
            return wrap("DELETE FROM dwd_trade_order_detail")

        # 问题5（演示 Schema 校验拦截）：包含不存在的列
        if "利润" in q or "profit" in ql:
            return wrap("SELECT dt, profit_amt FROM dws_trade_order_di LIMIT 10")

        # 兜底：保守探查
        return wrap("SELECT dt, order_cnt, pay_amt FROM dws_trade_order_di ORDER BY dt DESC LIMIT 10")

    # ------------------------------------------------------------------
    def _summarize(self, prompt: str) -> str:
        # 从 prompt 中粗略抽取行数，给出一句话总结
        m = re.search(r"共\s*(\d+)\s*行", prompt)
        n = m.group(1) if m else "若干"
        return f"查询成功返回 {n} 行数据，已按相关维度聚合/排序，可直接用于业务分析。"
