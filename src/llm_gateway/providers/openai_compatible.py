"""
OpenAI 兼容协议 Provider。

一份代码同时支持：
- DeepSeek-V3 API（方案 ADR-001 中"长上下文 + 低价"的 API 调用底座）
- 阿里云百炼 Qwen2.5-Coder（兼容模式）
- 本地 vLLM 部署的 Qwen2.5-Coder-32B（私有化、数据不出域）

因为它们都遵循 OpenAI 的 /chat/completions 协议，所以只需改 base_url / model / key。
"""
import httpx
from .base import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, base_url: str, model: str, api_key: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.name = f"openai_compatible:{model}"

    def complete(self, prompt: str, *, system: str = "", temperature: float = 0.0) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]
