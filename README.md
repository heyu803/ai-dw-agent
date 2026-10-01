# AI 数仓提效与 Agent 智能体（可运行参考实现）

> 一个**零外部依赖、本地即可端到端跑通**的 AI 数据仓库 Agent 项目，复刻并实现《AI 数仓提效与 Agent 智能体 — 技术方案设计文档 v2.0》的核心模块。
>
> 用 **SQLite + Mock LLM + 内置向量库** 让你在没有 GPU、没有 API Key、没有 Milvus/Neo4j 的情况下，也能完整看到一条自然语言查询是如何经过 **RAG 召回 → Schema Linking → SQL 生成 → 五层自校验 → 只读沙箱执行 → 结果格式化** 的全过程；同时预留了切换到真实 DeepSeek/Qwen、Milvus、PostgreSQL 的工厂入口。

---

## 这个项目能让你学到什么

如果你正在准备「AI 数仓 / LLM 应用 / Agent」相关岗位的面试，这个项目覆盖了几乎所有高频考点，并且**每一行核心代码都能跑、能改、能讲**：

- **Text-to-SQL Agent**：基于 LangGraph 的状态机编排，包含查询改写、RAG 召回、Schema Linking、SQL 生成、自校验、重试、沙箱执行的完整闭环。
- **五层自校验引擎**：语法（syntax）、Schema、安全（security）、语义（semantic）、性能（performance），对应文档里的「规则引擎 5 层校验」。
- **校验失败重试**：校验不通过时携带错误上下文回到 LLM 修正重生成，最多重试 2 次（对应文档流程图）。
- **只读沙箱**：用 SQLite `mode=ro` + 强制 `LIMIT` 注入，演示「只读沙箱执行」的安全隔离思想。
- **RAG 知识库**：向量检索 + 关键词检索 + **RRF 融合重排**，对应文档 3.3 节。
- **LLM Gateway**：多模型路由、降级容灾、Prompt 版本管理，对应文档第四章。
- **数据质量治理 Agent**：规则引擎、统计异常检测（Z-Score / IQR / Prophet）、根因分析血缘追溯，对应文档第七章。

> **重要提示**：项目默认使用一个 **Mock LLM**（基于关键词+模板的离线"假"模型）。它不是真模型，目的是让整条链路在零依赖下可复现地跑起来用于学习。把 `.env` 里的 `LLM_PROVIDER` 改成 `openai_compatible` 并填上 DeepSeek/Qwen 的地址和 Key，就能无缝换成真模型——这正是 LLM Gateway「provider 工厂模式」的价值。

---

## 30 秒快速开始

```bash
# 1. 安装依赖（建议 Python 3.10+）
pip install -r requirements.txt

# 2. 初始化示例电商数仓（SQLite，含 30 天数据 + 故意埋入的异常数据）
python -m scripts.init_db

# 3. 一键端到端演示（强烈建议先跑这个，能看到全链路轨迹）
python -m scripts.demo

# 4.（可选）启动 HTTP 服务，体验 API
uvicorn src.main:app --reload --port 8000
# 然后打开 http://127.0.0.1:8000/docs 看自动生成的 OpenAPI 文档
```

`python -m scripts.demo` 会依次演示 5 个自然语言查询（含 2 个故意被校验拦截的反例）和 3 个数据质量场景，**完整打印每一步链路轨迹**，是吃透本项目最快的入口。

---

## 项目结构

```
ai-dw-agent/
├── README.md                      # 你正在读的总说明书
├── requirements.txt               # 依赖（核心依赖零重型组件）
├── .env.example                   # 配置示例（复制为 .env 即可）
├── docs/                          # 分章节深度说明书（对照原文档章节）
│   ├── 01-architecture.md         #   一、系统整体架构
│   ├── 02-tech-selection.md       #   二、技术选型与 ADR 决策记录
│   ├── 03-rag.md                  #   三、RAG 知识库（含 RRF 融合）
│   ├── 04-llm-gateway.md          #   四、LLM Gateway 与 Prompt 管理
│   ├── 05-text-to-sql.md          #   五、Text-to-SQL Agent（LangGraph 状态机 + 五层校验）
│   ├── 06-dq-agent.md             #   七、数据质量治理 Agent
│   └── 07-interview-qa.md         #   面试问答宝典（高频题 + 参考答案）
├── scripts/
│   ├── init_db.py                 # 建库脚本：示例电商数仓 + 埋点异常数据
│   └── demo.py                    # 端到端 CLI 演示
└── src/
    ├── config.py                  # pydantic-settings 配置中心
    ├── warehouse_schema.py        # 数仓表结构（单一数据源，供 RAG 与校验共用）
    ├── schemas/models.py          # 全局数据模型（校验层枚举、请求/响应体等）
    ├── llm_gateway/               # 四、LLM Gateway
    │   ├── gateway.py             #   统一入口 + 降级容灾
    │   ├── prompt_manager.py      #   Prompt 版本管理
    │   └── providers/             #   provider 工厂：mock / openai_compatible
    ├── rag/                       # 三、RAG 知识库
    │   ├── embedding.py           #   轻量 embedding（生产换 BGE-M3）
    │   ├── vector_store.py        #   内置向量库（生产换 Milvus）
    │   ├── reranker.py            #   关键词检索 + RRF 融合重排
    │   └── pipeline.py            #   Schema 知识库（建索引 + 召回）
    ├── agents/
    │   ├── orchestrator.py        # Agent 编排器（装配各组件）
    │   ├── text_to_sql/           # 五、Text-to-SQL Agent
    │   │   ├── state.py           #   LangGraph 状态定义
    │   │   ├── graph.py           #   状态机编排（核心！）
    │   │   ├── schema_linking.py  #   5.2 Schema Linking
    │   │   ├── sql_generator.py   #   5.3.1 SQL 生成（首次/修正）
    │   │   ├── validator.py       #   5.3.2 五层自校验引擎
    │   │   └── sandbox.py         #   5.4 只读执行沙箱
    │   └── data_quality/          # 七、数据质量治理 Agent
    │       ├── rule_engine.py     #   7.1 规则型检测引擎
    │       ├── anomaly_detector.py#   7.2 统计异常检测
    │       └── root_cause.py      #   7.3 根因分析推理链
    └── api/                       # 一、应用服务层（BFF）
        ├── query.py               #   /api/v1/query/generate
        └── dq.py                  #   /api/v1/dq/check, /root-cause
```

---

## 离线数仓部分（warehouse-hive/）

项目还包含一套**离线数仓五层建模实践**（物流域，Hive/Spark SQL），与上面的 AI Agent 形成「大数据 + AI」双线：

- `warehouse-hive/` 演示 ODS → DIM/DWD → DWS → ADS 五层建表（Parquet + 按日分区）；
- 覆盖维度建模（星型模型、SCD2 拉链表）、增量去重、数据倾斜治理（加盐打散 + 二次聚合）、
  小文件合并、Map Join 等离线数仓核心点，详见 [warehouse-hive/README.md](warehouse-hive/README.md)。

> 离线数仓部分是 Hadoop/Hive 环境的**建模参考 SQL**，不依赖本项目的 Python 运行链路。

---

## 推荐的学习路径（如何"吃透"）

1. **先跑 `python -m scripts.demo`**，把输出从头读到尾，建立"全链路长什么样"的直觉。
2. **读 `docs/01-architecture.md`**，理解五层分层架构与调用时序。
3. **打开 `src/agents/text_to_sql/graph.py`**，对照 `docs/05-text-to-sql.md`，这是整个项目的灵魂——一个 LangGraph 状态机。重点理解条件边路由（校验通过/重试/拦截/重试耗尽）。
4. **读 `src/agents/text_to_sql/validator.py`**，逐层看五层校验是怎么实现的，尤其是安全层为什么用 AST 而不是只用正则。
5. **读 `docs/03-rag.md` + `src/rag/reranker.py`**，搞懂 RRF 融合公式 `score = Σ 1/(k + rank)`。
6. **读 `docs/06-dq-agent.md`**，理解数据质量三件套（规则/统计/根因）。
7. **最后通读 `docs/07-interview-qa.md`**，把"会写"升级成"会讲"。

---

## 从 Mock 切换到真实组件

项目用工厂模式把"教学实现"和"生产实现"解耦，切换只改配置不改业务代码：

| 能力 | Mock / 内置实现（默认） | 生产实现 | 切换方式 |
|---|---|---|---|
| LLM | `MockLLMProvider`（关键词模板） | DeepSeek-V3 / Qwen2.5-Coder（OpenAI 兼容 API） | `.env` 设 `LLM_PROVIDER=openai_compatible` + 填 `LLM_BASE_URL/MODEL/API_KEY` |
| 向量库 | `BuiltinVectorStore`（内存余弦） | Milvus 2.4+ | `.env` 设 `VECTOR_STORE=milvus`（并实现对应分支） |
| Embedding | 字符 n-gram 哈希 | BGE-M3 | 替换 `src/rag/embedding.py` 的 `embed()` |
| 数仓 | SQLite | PostgreSQL / Presto / StarRocks | `.env` 设 `WAREHOUSE_URL`（并接 SQLAlchemy/对应驱动） |
| 血缘图谱 | 内置字典 `LINEAGE` | Neo4j 5.x | 替换 `root_cause.py` 的 `get_upstream_chain` 为 Cypher 查询 |

---

## 免责声明

本项目是基于公开技术方案文档的**学习用参考实现**，示例数据均为脚本随机生成。Mock LLM 仅用于教学演示，不具备真实模型的推理能力。生产落地请接入真实模型与组件，并补充鉴权、限流、可观测性、单元/集成测试等工程能力。
