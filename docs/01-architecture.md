# 一、系统整体架构

> 对应原方案第一章。本章讲清楚：架构分了哪几层、每层放什么、一条查询是怎么在这些层之间流动的。

## 1.1 架构设计原则

这套系统遵循几条核心原则，理解它们能帮你回答"为什么这么设计"：

1. **分层解耦**：应用层只管编排和对外，AI 能力层（LLM/RAG）作为可替换的"中间件"，数据层作为持久化底座。任何一层的实现都能被替换而不影响其它层。
2. **Agent 而非单次调用**：Text-to-SQL 不是"问一次 LLM 拿到 SQL 就完事"，而是一个带**状态、循环、条件分支、自我修正**的状态机。这是 Agent 与普通 LLM 调用的本质区别。
3. **安全优先、只读隔离**：面向数仓的取数场景，任何写操作都是不可接受的风险。系统在校验层（AST 判定）和执行层（只读沙箱）做了双重防护。
4. **可观测、可回溯**：每一步都写入 `trace`，每次 LLM 调用都记录 Prompt 版本号，便于排查"为什么生成了这条 SQL"。
5. **降级容灾**：主模型不可用时回退备用，保证服务可用性。

## 1.2 分层架构详解

原文档把系统分为五层，本项目按相同分层组织代码：

| 层 | 职责 | 原方案组件 | 本项目对应实现 |
|---|---|---|---|
| **应用服务层 (BFF)** | 对外 API、鉴权、路由分发、各业务 Service | Query/Review/DQ/ETL/Lineage Service | `src/api/`（FastAPI 路由） |
| **Agent 编排层 (Core)** | 任务调度、Agent 编排、工具注册 | Orchestrator / SQL Agent / Tool Registry | `src/agents/orchestrator.py` + `src/agents/text_to_sql/graph.py` |
| **AI 能力层 (Middleware)** | LLM 多模型路由、Prompt 管理、RAG 检索 | LLM Gateway / Prompt Manager / RAG Pipeline | `src/llm_gateway/` + `src/rag/` |
| **数据层 (Storage)** | 业务数据、缓存、向量、血缘、对象、消息 | PostgreSQL / Redis / Milvus / Neo4j / MinIO / RabbitMQ | SQLite（数仓）+ 内置向量库 + 内置血缘字典 |
| **基础设施层 (Infra)** | 容器编排、监控、日志、镜像、GitOps | K8s / Prometheus+Grafana / ELK / Harbor / ArgoCD | 本项目聚焦应用逻辑，基础设施留作部署阶段 |

> **面试点**：被问"为什么要有 BFF（Backend For Frontend）层"时，可答：BFF 把"前端/接入形态"（Web Console、VS Code 插件、飞书/企微 Bot、CLI）与"核心 Agent 能力"解耦，不同接入端可以有不同的鉴权、聚合、裁剪逻辑，而核心 Agent 保持单一稳定。

## 1.3 系统交互时序

以"业务自助取数"为例，一条自然语言查询的完整生命周期分为三个阶段（对应原文档时序图的 Phase 1/2/3）：

```
Phase 1（Request）
  User ──自然语言查询──▶ Gateway ──鉴权+路由──▶ QueryService

Phase 2（Orchestration，主流程）
  QueryService ──解析意图──▶ Orchestrator ──▶ SQL Agent
     Step1 查询改写
     Step2 RAG 召回 Schema（向量 + 关键词 → RRF 融合，Top-K）
     Step3 Schema Linking（裁剪出最相关的表/字段 + JOIN 提示）
     Step4 生成 SQL（首次：sql_generation Prompt）
     Step5 五层自校验
            ├─ PASS  ─────────────▶ 进入执行
            ├─ ERROR ─ retry<2 ──▶ 携带错误上下文回到 Step4 修正
            ├─ ERROR ─ retry≥2 ──▶ 返回错误（重试耗尽）
            └─ BLOCKER ──────────▶ 直接拦截返回（如 DELETE）
     Step6 只读沙箱执行
     Step7 结果格式化（LLM 生成自然语言总结）

Phase 3（Response）
  SQL Agent ──QueryResult──▶ ... ──▶ User（200 OK：SQL + 数据 + 一句话总结）
```

在本项目里，这条链路就是 `src/agents/text_to_sql/graph.py` 里的 LangGraph 状态机。跑一次 `python -m scripts.demo` 就能看到上面每个 Step 被真实打印出来（`trace` 轨迹）。

## 关键文件索引

- 编排入口：`src/agents/orchestrator.py`
- 状态机：`src/agents/text_to_sql/graph.py`
- 对外 API：`src/api/query.py`、`src/api/dq.py`、`src/main.py`
- 配置中心：`src/config.py`
