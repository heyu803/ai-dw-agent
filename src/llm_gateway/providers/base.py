"""
LLM Provider 抽象层。

对应方案"四、LLM Gateway 与模型管理"：
所有模型（私有部署的 Qwen2.5-Coder、API 调用的 DeepSeek-V3）都实现统一接口，
上层 Agent 不感知底层是哪个模型 —— 这是多模型路由 / 降级容灾的基础。
"""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """统一的 LLM 调用接口。"""

    name: str = "base"

    @abstractmethod
    def complete(self, prompt: str, *, system: str = "", temperature: float = 0.0) -> str:
        """单轮补全。返回模型输出的纯文本。"""
        raise NotImplementedError
