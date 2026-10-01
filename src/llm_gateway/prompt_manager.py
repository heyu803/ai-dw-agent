"""
Prompt 版本管理（对应方案 4.2 Prompt 版本管理）。

为什么 Prompt 要做版本管理（面试高频）：
- Prompt 是 Agent 的"源代码"，效果对 Prompt 极其敏感；
- 需要可灰度、可回滚、可 A/B 对比、可审计"哪一版 Prompt 产出了哪个结果"；
- 这里用内存字典 + 版本号做最小实现；生产可落到 PostgreSQL/配置中心，
  并记录每次调用使用的 prompt_version 到 trace 里。
"""
from dataclasses import dataclass


@dataclass
class PromptTemplate:
    name: str
    version: str
    template: str

    def render(self, **kwargs) -> str:
        return self.template.format(**kwargs)


class PromptManager:
    def __init__(self):
        self._store: dict[str, PromptTemplate] = {}
        self._register_defaults()

    def register(self, tpl: PromptTemplate):
        self._store[tpl.name] = tpl

    def get(self, name: str) -> PromptTemplate:
        if name not in self._store:
            raise KeyError(f"未注册的 Prompt: {name}")
        return self._store[name]

    def _register_defaults(self):
        # ---- SQL 生成 Prompt ----
        self.register(PromptTemplate(
            name="sql_generation",
            version="v1.2",
            template=(
                "你是一名资深数仓 SQL 工程师。请根据【用户问题】和【可用表结构】生成一条标准 SQL。\n\n"
                "要求：\n"
                "1. 只允许 SELECT 查询，禁止任何写操作；\n"
                "2. 只能使用下面给出的表和字段，不要臆造字段；\n"
                "3. 涉及大表请加合理的过滤/分区条件；\n"
                "4. 用 ```sql ``` 包裹最终 SQL，不要输出多余解释。\n\n"
                "【用户问题】\n{question}\n\n"
                "【可用表结构】\n{schema}\n"
            ),
        ))

        # ---- SQL 修正 Prompt（携带错误上下文重试，对应图中 'LLM 修正生成 携带错误上下文'）----
        self.register(PromptTemplate(
            name="sql_fix",
            version="v1.1",
            template=(
                "你之前生成的 SQL 校验未通过，请修正后重新输出。\n\n"
                "【用户问题】\n{question}\n\n"
                "【可用表结构】\n{schema}\n\n"
                "【上一版 SQL】\n{previous_sql}\n\n"
                "【校验错误】\n{errors}\n\n"
                "请针对上述错误修正，仍用 ```sql ``` 包裹最终 SQL。"
            ),
        ))

        # ---- 语义校验 Prompt（对应五层校验中的语义层）----
        self.register(PromptTemplate(
            name="semantic_check",
            version="v1.0",
            template=(
                "请判断下面的 SQL 是否正确回答了用户问题（semantic check）。\n"
                "只输出 JSON：{{\"match\": true/false, \"reason\": \"...\"}}\n\n"
                "【用户问题】{question}\n【SQL】{sql}\n"
            ),
        ))

        # ---- 结果总结 Prompt ----
        self.register(PromptTemplate(
            name="answer_summary",
            version="v1.0",
            template=(
                "请用一句话总结查询结果（summarize），面向业务同学，简洁专业。\n"
                "【用户问题】{question}\n【结果共 {row_count} 行，列：{columns}】\n【样本数据】{sample}\n"
            ),
        ))
