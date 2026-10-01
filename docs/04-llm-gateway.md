# 四、LLM Gateway 与模型管理

> 对应原方案第四章。LLM Gateway 是整套系统的"流量入口"，所有模型调用都从这里走。本章讲多模型路由、降级容灾、Prompt 版本管理、推理优化。

## 4.1 多模型路由策略

不同任务对模型的诉求不同：
- **SQL 生成**：要代码能力强 → Qwen2.5-Coder（私有）；
- **长文档总结**：要长上下文 + 低成本 → DeepSeek-V3（API）；
- **简单语义判断**：要快 + 便宜 → 小模型即可。

所以 Gateway 要根据**任务类型 / 成本预算 / 上下文长度 / 数据敏感级别**把请求路由到合适的模型。

本项目用 **provider 工厂模式**实现可切换：
- `src/llm_gateway/providers/base.py`：定义 `LLMProvider` 抽象基类（`complete` 方法）；
- `mock.py`：离线 Mock 模型（默认，零依赖可跑）；
- `openai_compatible.py`：对接任何 OpenAI 兼容 API（DeepSeek / Qwen vLLM / 通义 等）。

`build_gateway()` 根据 `.env` 的 `LLM_PROVIDER` 选择主 provider。生产里可以在这里扩展成"按任务类型选不同 provider 实例"的真正路由表。

## 4.2 降级容灾

```python
class LLMGateway:
    def complete(self, prompt, ...):
        try:
            return self.primary.complete(prompt, ...)   # 主模型
        except Exception:
            return self.fallback.complete(prompt, ...)   # 失败降级到备用
```

主模型不可用（超时、限流、宕机）时自动回退到备用模型（本项目演示回退到 Mock，保证 demo 永远有响应）。生产里 fallback 通常是另一个真实模型或缓存结果。

> **面试点**：被问"模型挂了怎么办"——答：Gateway 层做熔断+降级，主备多活；再配合超时控制、重试退避、限流，避免雪崩。

## 4.3 Prompt 版本管理

**Prompt 是 Agent 的"源代码"**，效果对 Prompt 极其敏感。改一个字都可能让生成质量变化，因此必须像管代码一样管 Prompt：

- **版本号**：每个 Prompt 带 `version`，便于灰度、回滚、A/B；
- **可审计**：每次调用记录用了哪一版 Prompt（写入日志/trace），出问题能回溯"是哪版 Prompt 产出的结果"；
- **集中管理**：所有 Prompt 收口到 `PromptManager`，不散落在业务代码里。

本项目 `src/llm_gateway/prompt_manager.py` 注册了 4 个带版本号的 Prompt：

| 名称 | 版本 | 用途 |
|---|---|---|
| `sql_generation` | v1.2 | 首次生成 SQL |
| `sql_fix` | v1.1 | 校验失败后携带错误上下文修正重生成 |
| `semantic_check` | v1.0 | 语义层校验（SQL 是否回答了问题） |
| `answer_summary` | v1.0 | 把查询结果总结成一句话 |

`gateway.complete_with_prompt("sql_generation", question=..., schema=...)` 会先渲染模板、记录版本号、再调用模型。

> **面试点**：Prompt 工程的工程化——版本管理、效果评估（建测试集跑准确率）、灰度发布、回滚机制。能讲出"Prompt 也要 CI/CD"就很到位。

## 4.4 推理性能优化

原方案提到的推理优化方向（本项目未全部实现，但要会讲）：
- **批处理（batching）**：把并发请求合并成 batch 提高 GPU 利用率；
- **KV Cache / Prefix Cache**：复用相同前缀（如系统 Prompt）的计算；
- **量化**：INT8/INT4 量化降低显存与延迟；
- **流式输出（streaming）**：边生成边返回，降低首字延迟体感；
- **结果缓存**：相同问题命中缓存直接返回（注意数据时效性）；
- **推理引擎**：用 vLLM / TGI 做高吞吐部署（PagedAttention 等）。

## 关键文件索引

- `src/llm_gateway/gateway.py`：统一入口 + 降级
- `src/llm_gateway/prompt_manager.py`：Prompt 版本管理
- `src/llm_gateway/providers/base.py`：provider 抽象
- `src/llm_gateway/providers/mock.py`：离线 Mock 模型
- `src/llm_gateway/providers/openai_compatible.py`：真实 API 接入
