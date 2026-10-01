# 五、Text-to-SQL Agent 技术实现

> 对应原方案第五章 + 图2 完整调用时序 + 图3/4 校验·重试决策流程。**这是整个项目的核心，也是面试最深入的部分。** 务必对照 `src/agents/text_to_sql/graph.py` 阅读。

## 5.1 Agent 状态机设计（LangGraph）

### 为什么用状态机，而不是"调一次 LLM 拿 SQL"？

一个朴素的 Text-to-SQL 是：`问题 → LLM → SQL → 执行`。但这条直线在生产里会处处翻车：
- LLM 可能生成**语法错误**的 SQL（跑不起来）；
- 可能**幻觉字段**（编出不存在的列）；
- 可能生成**危险操作**（DROP/DELETE）；
- 可能**答非所问**（能跑但语义跑偏）；
- 可能**性能炸裂**（全表扫描）。

所以正确的 Text-to-SQL 是一个**带状态、带循环、带条件分支、能自我修正**的流程。这正是 LangGraph 的状态机模型擅长表达的。

### 状态（State）

`src/agents/text_to_sql/state.py` 用 `TypedDict` 定义贯穿全流程的状态，关键字段：
- `question` / `rewritten_question`：原始问题 / 改写后问题；
- `retrieved_tables`：RAG 召回的候选表；
- `linked_schema`：Schema Linking 裁剪后喂给 LLM 的表结构；
- `sql`：当前 SQL；
- `validations`：五层校验结果列表；
- `validation_ok`：是否全部通过（无 ERROR/BLOCKER）；
- `retry_count`：已重试次数；
- `rows` / `columns` / `row_count`：执行结果；
- `answer`：自然语言总结；
- `error` / `success`：终态；
- `trace`：全链路轨迹（每步都 append，方便观测）。

### 节点与边（Node & Edge）

```
START → rewrite → retrieve → schema_link → generate → validate → [条件路由]
                                              ▲                         │
                                              │                         ├─ ok        → execute → [条件路由] ─ ok     → format → END
                                              │                         │                                  └─ failed → return_error → END
                                              └── prepare_retry ◀───────┤─ retry     （retry_count < N）
                                                                        ├─ blocked   → return_error → END   （命中 BLOCKER，不重试）
                                                                        └─ exhausted → return_error → END   （重试耗尽）
```

每个节点对应文档时序图的一个 Step：
| 节点 | Step | 职责 |
|---|---|---|
| `rewrite` | Step1 | 查询改写（demo 透传；生产做指代消解、口径补全、多轮融合） |
| `retrieve` | Step2 | RAG 召回候选表（向量+关键词+RRF） |
| `schema_link` | Step3 | Schema Linking：裁剪最相关表/字段 + JOIN 提示 |
| `generate` | Step4 | 生成 SQL（首次）/ 修正 SQL（带错误上下文重试） |
| `validate` | Step5 | 五层自校验 |
| `prepare_retry` | — | 递增 retry_count（见下方"关键坑"） |
| `execute` | Step6 | 只读沙箱执行 |
| `format` | Step7 | 结果格式化为自然语言 |
| `return_error` | — | 拦截/失败的统一终态 |

### 一个真实踩过的坑（面试可讲）

**条件边的路由函数里不能修改 state**。最初我把 `retry_count += 1` 写在 `route_after_validate` 路由函数里，结果陷入无限循环（`GraphRecursionError`）。

原因：LangGraph 里**路由函数是"只读决策器"**，它返回一个走向标签，对 state 的修改不会被持久化；**只有节点（Node）对 state 的修改才会进入下一轮状态**。所以正确做法是新增一个专门的 `prepare_retry` 节点来递增计数器，路由函数只读 state 做判断。

```python
# ❌ 错误：在路由函数里改 state（不持久化 → 死循环）
def route_after_validate(state):
    state["retry_count"] += 1   # 这行改了个寂寞
    ...

# ✅ 正确：路由只读判断，递增放进专门的节点
def route_after_validate(state):
    if state.get("retry_count", 0) < MAX_RETRY:
        return "retry"          # → prepare_retry 节点
    return "exhausted"

def prepare_retry_node(state):
    state["retry_count"] += 1   # 在节点里改才会持久化
    return state
```

> 这个坑非常能体现"是否真的写过 LangGraph"，面试讲出来很有说服力。

## 5.2 Schema Linking 模块

RAG 召回了候选表后，还要做 **Schema Linking**：从候选表里进一步确定"这次查询到底要用哪些表、哪些字段、表之间怎么 JOIN"，然后渲染成简洁的上下文喂给 LLM。

- 对应代码：`src/agents/text_to_sql/schema_linking.py`
- 关键：内置 `JOIN_HINTS`（表间关联关系提示），帮助 LLM 正确生成 JOIN 条件，减少幻觉。

> **面试点**：RAG 召回（粗筛"哪些表相关"）和 Schema Linking（精选"用哪些字段+怎么 JOIN"）是两个层次。把它们分开能让上下文更精准，显著降低生成错误率。

## 5.3 SQL 生成与自校验引擎

### 5.3.1 SQL 生成核心逻辑

`src/agents/text_to_sql/sql_generator.py`：
- **首次生成**：用 `sql_generation` Prompt + Schema Linking 结果；
- **修正重试**：校验失败时用 `sql_fix` Prompt，**携带"上一版 SQL + 校验错误"**重生成——这就是图里的"LLM 修正生成 携带错误上下文"；
- `_extract_sql()` 鲁棒解析 LLM 输出里的 ` ```sql ``` ` 代码块（兼容裸 SQL）。

### 5.3.2 多层自校验引擎（重点）

`src/agents/text_to_sql/validator.py` 实现五层校验，**由轻到重、由确定到模糊**：

| 层 | 校验内容 | 严重级别 | 命中后果 |
|---|---|---|---|
| **L1 语法 syntax** | sqlglot 能否解析 | ERROR | 可重试修正 |
| **L2 Schema** | 表/列是否真实存在（防幻觉） | ERROR | 可重试修正 |
| **L3 安全 security** | 是否只读、是否含 DROP/DELETE 等 | **BLOCKER** | **直接拦截，不重试** |
| **L4 语义 semantic** | LLM 判断 SQL 是否回答了问题 | WARN | 记录风险，不阻断 |
| **L5 性能 performance** | SELECT \* / 明细大表无 LIMIT / 无分区过滤 | WARN | 记录风险，不阻断 |

**严重级别决定走向**（对应图3/4 流程）：
- `BLOCKER` → 直接返回错误（如 DELETE 被安全层拦截），**不重试**；
- `ERROR` → 若 `retry_count < N`（默认 N=2）则带错误上下文重试，否则返回"重试耗尽"错误；
- `WARN` → 不阻断，记录后继续执行；
- 全 `PASS` → 进入沙箱执行。

#### 两个值得讲的实现细节

**① 安全层为什么用 AST 而不是只用正则？**

```python
# 正则快速拦截危险关键词
if DANGEROUS.search(sql):  # DROP/DELETE/TRUNCATE/INSERT/UPDATE/ALTER/...
    return BLOCKER
# 但正则会被绕过（注释、大小写、字符串里的关键词），所以再用 AST 兜底：
# 只要解析出来的根节点不是 SELECT/UNION/Subquery，一律拦截
if not isinstance(parsed, (exp.Select, exp.Union, exp.Subquery)):
    return BLOCKER
```

正则负责"快"，AST 负责"准"。**双重判定**：正则做关键词黑名单快速拦截，AST 做"语句类型必须是只读查询"的白名单兜底。这样既快又难绕过。

**② Schema 校验如何避免把 SQL 别名误判为不存在的列？**

`SELECT SUM(pay_amt) AS total_amt` 里的 `total_amt` 是别名，不是真实列。如果直接拿所有 `Column` 去比对表字段，就会把 `total_amt` 误判为"不存在的字段"。

解法：先用 `parsed.find_all(exp.Alias)` 收集所有别名，校验列时把别名排除掉。

```python
aliases = {a.alias.lower() for a in parsed.find_all(exp.Alias) if a.alias}
for col in parsed.find_all(exp.Column):
    if col.name.lower() in aliases:  # 是别名，跳过
        continue
    # ... 否则才校验是否是真实列
```

> **面试点**：这两个细节非常能体现"做过真实 Text-to-SQL"。能讲出"正则+AST 双重安全判定"和"别名要从列校验里排除"，远比只说"我做了 SQL 校验"有说服力。

## 5.4 执行沙箱

`src/agents/text_to_sql/sandbox.py`：
- **只读连接**：SQLite 用 `file:...?mode=ro` 以只读模式打开，从连接层面杜绝写操作（即使前面校验漏了，这里也写不进去）；
- **强制 LIMIT 注入**：用 sqlglot 给没有 LIMIT 的查询自动注入 `LIMIT 200`，防止误取海量数据把服务打挂；
- **生产对应**：换成对数仓的只读账号 + 资源队列 + 超时控制 + 行数上限。

> **面试点**："只读沙箱"是纵深防御的最后一道——**校验层防"生成危险 SQL"，执行层防"万一漏过也执行不了"**。安全要做多层，不能只信任单点。

## 跑一遍看效果

```bash
python -m scripts.demo
```

你会看到 5 个问题里：
- 前 3 个正常生成并执行（含两个 JOIN 查询）；
- 第 4 个"删除订单明细表" → 安全层 **BLOCKER 拦截**，不执行；
- 第 5 个"查利润金额"（`profit_amt` 字段不存在）→ Schema 层 **ERROR**，**重试 2 次仍失败 → 返回"重试耗尽"错误**。

这正好把状态机的四条出边（ok / retry→exhausted / blocked）全部演示了一遍。
