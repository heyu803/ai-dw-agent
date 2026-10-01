"""
LLM Gateway —— 模型调用的统一入口（对应方案"四、LLM Gateway 与模型管理"）。

职责（面试可讲，这是整套系统的"流量入口"）：
1. 多模型路由：按任务类型 / 成本 / 上下文长度选择模型（4.1 多模型路由策略）；
2. 降级容灾：主模型失败时回退到备用模型（这里演示回退到 mock，保证可用性）；
3. 统一 Prompt 入口：所有调用都经过 PromptManager，便于版本管理与审计；
4. （生产可扩展）限流熔断、Token 计费、调用链埋点。
"""
import logging
from .providers.base import LLMProvider
from .providers.mock import MockLLMProvider
from .providers.openai_compatible import OpenAICompatibleProvider
from .prompt_manager import PromptManager
from ..config import get_settings

logger = logging.getLogger(__name__)


class LLMGateway:
    def __init__(self, primary: LLMProvider, fallback: LLMProvider | None = None):
        self.primary = primary
        self.fallback = fallback or MockLLMProvider()
        self.prompts = PromptManager()

    # ---- 直接补全（已渲染好的 prompt）----
    def complete(self, prompt: str, *, system: str = "", temperature: float = 0.0) -> str:
        try:
            return self.primary.complete(prompt, system=system, temperature=temperature)
        except Exception as e:  # noqa: BLE001 —— 网关层需要兜住一切异常做降级
            logger.warning("主模型 %s 调用失败，降级到 %s：%s", self.primary.name, self.fallback.name, e)
            return self.fallback.complete(prompt, system=system, temperature=temperature)

    # ---- 经 PromptManager 渲染后再补全 ----
    def complete_with_prompt(self, prompt_name: str, *, temperature: float = 0.0, **vars) -> str:
        tpl = self.prompts.get(prompt_name)
        rendered = tpl.render(**vars)
        logger.info("使用 Prompt %s@%s 调用模型 %s", tpl.name, tpl.version, self.primary.name)
        return self.complete(rendered, temperature=temperature)


def build_gateway() -> LLMGateway:
    """根据配置构建 Gateway（工厂方法）。"""
    s = get_settings()
    if s.llm_provider == "openai_compatible":
        primary = OpenAICompatibleProvider(
            base_url=s.llm_base_url, model=s.llm_model, api_key=s.llm_api_key
        )
    else:
        primary = MockLLMProvider()
    # 任何 provider 失败都回退到 mock，保证 demo / 演示永远有响应
    return LLMGateway(primary=primary, fallback=MockLLMProvider())
