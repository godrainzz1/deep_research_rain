# DeepResearch 项目完全指南

> 面向面试准备的逐文件讲解。建议按顺序阅读，每读完一节对照源码看一遍。

---

## 目录

1. [项目概览](#1-项目概览)
2. [技术栈速览](#2-技术栈速览)
3. [架构全景图](#3-架构全景图)
4. [一次完整研究的生命周期](#4-一次完整研究的生命周期)
5. [核心层：agent.py](#5-核心层agentpy)
6. [配置层：config.py](#6-配置层configpy)
7. [数据模型：models.py](#7-数据模型modelspy)
8. [Prompt 层：prompts.py](#8-prompt-层promptspy)
9. [工具层：utils.py](#9-工具层utilspy)
10. [服务层](#10-服务层)
    - [10.1 planner.py — 任务规划](#101-plannerpy--任务规划)
    - [10.2 search.py — 搜索调度](#102-searchpy--搜索调度)
    - [10.3 search_quality.py — 搜索质量](#103-search_qualitypy--搜索质量)
    - [10.4 summarizer.py — 任务总结](#104-summarizerpy--任务总结)
    - [10.5 reporter.py — 报告生成](#105-reporterpy--报告生成)
    - [10.6 notes.py — 笔记协作](#106-notepy--笔记协作)
    - [10.7 text_processing.py — 文本清洗](#107-text_processingpy--文本清洗)
    - [10.8 tool_events.py — 工具事件追踪](#108-tool_eventspy--工具事件追踪)
    - [10.9 pipeline.py — 管道框架](#109-pipelinepy--管道框架)
    - [10.10 skill_engine.py — 技能引擎](#1010-skill_enginepy--技能引擎)
11. [RAG 引擎层](#11-rag-引擎层)
    - [11.1 parser.py — 文件解析](#111-parserpy--文件解析)
    - [11.2 chunker.py — 文本分块](#112-chunkerpy--文本分块)
    - [11.3 embedder.py — 向量嵌入](#113-embedderpy--向量嵌入)
    - [11.4 store.py — 向量存储](#114-storepy--向量存储)
    - [11.5 retriever.py — 混合检索](#115-retrieverpy--混合检索)
    - [11.6 ingest.py — 摄入管道](#116-ingestpy--摄入管道)
12. [记忆层：memory/store.py](#12-记忆层memorystorepy)
13. [入口层：main.py](#13-入口层mainpy)
14. [前端层：App.vue](#14-前端层appvue)
15. [Skill 定义文件](#15-skill-定义文件)
16. [依赖关系图](#16-依赖关系图)

---

## 1. 项目概览

**DeepResearch** 是一个 AI 深度研究助手。用户输入任意话题，系统自动：

1. 将话题拆解为 3~5 个互补的子任务
2. 对每个子任务进行网络搜索
3. 逐任务生成结构化的要点总结
4. 汇总所有子任务，生成带引用来源的最终报告

整个过程通过 SSE（Server-Sent Events）实时推送到前端，用户可以看到 Agent 搜索了什么、找到了哪些来源、正在写什么内容。

---

## 2. 技术栈速览

| 层级 | 技术 | 作用 |
|---|---|---|
| Web 框架 | FastAPI | 暴露 REST API + SSE 流式端点 |
| Agent 框架 | HelloAgents | 提供 LLM 调用抽象、Tool 注册、流式对话管理 |
| 向量数据库 | ChromaDB | 存储文档 Embedding，支持语义检索 |
| 关系数据库 | SQLite | 存储研究历史、用户偏好、FAQ |
| LLM 提供商 | DashScope (阿里云) | 主力模型 qwen3.6-max-preview |
| 本地 LLM | Ollama | Embedding 模型 + LLM 降级兜底 |
| 前端 | Vue 3 + TypeScript | SPA 界面，SSE 消费 |
| 文档解析 | PyMuPDF, python-docx | PDF/Word 解析 |

### 每个技术"为什么选它"

| 技术 | 选型理由 |
|---|---|
| FastAPI | Python 异步原生支持，SSE 只需 `StreamingResponse`，自带 OpenAPI 文档 |
| HelloAgents | 项目原型基于它，封装了 LLM 多提供商切换、Tool 注册、流式解析 |
| ChromaDB | Python 原生、嵌入式运行无需单独服务、持久化零配置 |
| SQLite | 嵌入式、零配置、适合单用户本地运行 |
| SSE | 单向推送（服务端→前端），比 WebSocket 轻量，浏览器 `EventSource` 原生支持自动重连 |
| Ollama | 本地免费、中文 Embedding 模型（qwen3-embedding）效果好 |

---

## 3. 架构全景图

```
┌──────────────────────────────────────────────────────────┐
│                    前端 Vue 3 (App.vue)                    │
│  输入话题 → 实时展示搜索/总结/报告 ← SSE 流式接收          │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP POST /research/stream (SSE)
┌──────────────────────┴───────────────────────────────────┐
│                  FastAPI 网关 (main.py)                    │
│  /research/stream · /knowledge/upload · /memory/history   │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────────┐
│              Agent 编排层 (agent.py)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                │
│  │ Planner  │→ │ Executor │→ │ Reporter │                │
│  │ (拆任务) │  │(搜+总结) │  │ (出报告) │                │
│  └──────────┘  └──────────┘  └──────────┘                │
│        ↓            ↓             ↓                       │
│  SkillEngine    SearchTool    NoteTool                    │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────────┐
│                      引擎层                                │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Search  │  │   RAG    │  │  Memory  │  │   LLM    │  │
│  │ Tavily  │  │ChromaDB  │  │ SQLite   │  │DashScope │  │
│  │ SerpApi │  │Embedding │  │ Semantic │  │ Ollama   │  │
│  │DuckDuck │  │ TF-IDF   │  │  Memory  │  │(fallback)│  │
│  └─────────┘  └──────────┘  └──────────┘  └──────────┘  │
└──────────────────────────────────────────────────────────┘
```

### 四层架构

| 层级 | 职责 | 关键文件 |
|---|---|---|
| 前端 | 用户交互、SSE 消费、Markdown 渲染 | `App.vue` |
| 网关 | HTTP 路由、请求验证、SSE 封装 | `main.py` |
| 编排 | 任务规划→执行→报告的主循环 | `agent.py` |
| 引擎 | 搜索、RAG、记忆、LLM 调用 | `rag/`, `memory/`, `services/` |

---

## 4. 一次完整研究的生命周期

用户在前端输入 "2025年AI Agent 框架有哪些？" 点击开始研究。以下是完整流程：

### 阶段 0：请求到达 (main.py)

```
前端 POST /research/stream {"topic": "2025年AI Agent 框架有哪些？"}
  → main.py 接收请求
  → 创建 DeepResearchAgent 实例
  → 调用 agent.run_stream(topic)
  → 返回 StreamingResponse (SSE)
```

### 阶段 1：Skill 匹配 (agent.py: run_stream)

```python
# agent.py run_stream()
matched = skill_engine.match(topic)  # "deep-research"
# 前端收到: {"type": "skill", "name": "deep-research"}
```

### 阶段 2：任务规划 (planner.py)

```
planner.plan_todo_list(state)
  → 构建 prompt（含话题、当前日期）
  → 调用 LLM（规划专家 Agent）
  → LLM 返回 JSON: {"tasks": [{"title":"...","intent":"...","query":"..."}]}
  → 每个 task 通过 NoteTool 创建笔记
  → 前端收到: {"type": "todo_list", "tasks": [...]}
```

### 阶段 3：逐任务执行 (agent.py: _execute_task)

对每个子任务并发执行：

```
_execute_task(state, task)
  → dispatch_search(query)       # 搜索
  → score_and_filter_results()   # 质量评分
  → deduplicate_results()        # 去重
  → prepare_research_context()   # 格式化上下文 (含 RAG)
  → summarizer.summarize_task()  # LLM 总结（流式）
  → mark task.completed
```

每一步都有 SSE 事件推送前端。

### 阶段 4：报告生成 (reporter.py)

```
reporting.generate_report(state)
  → 收集所有 task.summary + task.sources_summary
  → 构建 prompt（含所有任务结果）
  → 调用 LLM（报告撰写专家 Agent）
  → 返回结构化 Markdown 报告
  → 前端收到: {"type": "final_report", "report": "..."}
```

### 阶段 5：持久化 (memory/store.py)

```
memory_store.save_session(session_id, topic, report)
  → 写入 SQLite sessions 表
  → 可选：生成知识卡片 → ChromaDB semantic_memory
```

---

## 5. 核心层：agent.py

**文件位置**：`backend/src/agent.py`
**职责**：整个项目的大脑。协调 Planner、Executor、Reporter 三个角色的协作。

### 5.1 FallbackLLM 类

熔断降级包装器。代理对 HelloAgentsLLM 的 `stream_invoke()` 和 `invoke()` 调用。

**工作流程**：
```
请求 → primary.stream_invoke()
         ↓ 成功 → 返回结果
         ↓ 失败 → _primary_dead = True
                  → fallback.stream_invoke()
                  → 后续所有调用直接走 fallback（不再重试 primary）
```

**为什么用熔断而不是每次重试**：如果 primary 因为 API 余额耗尽返回 403，每次重试都会浪费一个 HTTP 往返（~1-2 秒），且产生无效 API 请求。熔断一次判断后全部直走 fallback。

**面试要点**：`__getattr__` 将所有属性访问委托给 primary，所以下游代码（ToolAwareSimpleAgent）不需要知道 FallbackLLM 的存在——它看起来就像一个普通的 HelloAgentsLLM。

### 5.2 DeepResearchAgent 类

#### 构造函数 __init__

```
1. 加载 Configuration
2. _init_llm() → 创建 primary + fallback LLM
3. 初始化 NoteTool（笔记工具）
4. 创建三个 Agent 实例：
   - todo_agent（规划专家，不需要 tool calling）
   - report_agent（报告专家，需要 note 工具读笔记）
   - _summarizer_factory（总结专家工厂函数）
5. 初始化服务：PlanningService, SummarizationService, ReportingService
```

#### _init_llm() — LLM 初始化

优先级链：`.env` 显式配置 > 系统环境变量自动检测 > 兜底默认值。

**DashScope 自动检测**：如果系统环境有 `DASHSCOPE_API_KEY` 且未显式设置 `LLM_BASE_URL`，自动设置为 DashScope 端点。

#### run() — 同步执行

```
plan_todo_list() → for task in tasks: _execute_task() → generate_report() → save to memory
```

#### run_stream() — 流式执行 ⭐ 最重要

这是面试中最可能被深挖的方法。

**关键设计决策**：

1. **线程 + 队列模型**：每个 task 启动一个线程执行，结果通过 `Queue` 汇总到主线程
2. **事件驱动的 SSE**：主线程在等待线程完成的同时，以 0.2s 间隔轮询队列，有事件立刻 yield
3. **为什么用线程而不是 asyncio**：HelloAgents 框架是同步的（基于 OpenAI 同步客户端），用线程适配到异步 FastAPI 是最小改动方案

```python
while alive > 0:
    event = event_queue.get(timeout=0.2)  # 0.2s 超时
    yield event                            # 立刻发给前端
    alive = sum(1 for t in threads if t.is_alive())
```

#### _execute_task() — 单任务执行

```
1. dispatch_search(query)     → 获取搜索结果
2. 如果无结果 → task.skipped
3. prepare_research_context() → 格式化上下文（web + RAG）
4. summarizer.summarize_task() 或 stream_task_summary() → LLM 总结
5. task.summary = summary_text
6. task.status = "completed"
```

---

## 6. 配置层：config.py

**文件位置**：`backend/src/config.py`
**职责**：集中管理所有配置项，支持三级来源（系统环境变量 > .env 文件 > 代码默认值）。

### Configuration 类（Pydantic BaseModel）

所有字段及其默认值：

```python
max_web_research_loops: int = 3        # 搜索迭代次数
local_llm: str = "llama3.2"           # 本地模型名
llm_provider: str = ""                 # ollama / lmstudio / 空=自动检测
search_api: SearchAPI = HYBRID        # 搜索后端
enable_notes: bool = True             # 启用笔记
notes_workspace: str = "./notes"      # 笔记目录
fetch_full_page: bool = True          # 获取完整页面
ollama_base_url: str = "http://localhost:11434"
strip_thinking_tokens: bool = True    # 剥离 <think> 标签
llm_max_tokens: int = 4096           # 最大输出 token（思考模型需要更多）
llm_timeout: int = 120               # LLM 超时（秒）
llm_fallback_provider: str = ""       # 降级提供商
```

**DashScope 自动检测**（line 165-166）：
```python
if os.getenv("DASHSCOPE_API_KEY") and not raw_values.get("llm_base_url"):
    raw_values.setdefault("llm_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
```

关键逻辑：`setdefault`——只在 `.env` 没设置时生效，不会覆盖显式配置。

### from_env() 类方法

1. 遍历所有 Field，检查 `os.environ` 中是否有同名大写变量
2. 应用 env_aliases 映射（处理 `LLM_API_KEY` → `DASHSCOPE_API_KEY` 的 fallback）
3. 执行 DashScope 自动检测
4. 应用传入的 overrides

---

## 7. 数据模型：models.py

**文件位置**：`backend/src/models.py`
**职责**：定义研究流程中流转的数据结构。

### TodoItem
```python
@dataclass
class TodoItem:
    id: int              # 任务编号
    title: str           # 任务标题
    intent: str          # 任务目标
    query: str           # 搜索查询词
    status: str = "pending"  # pending / in_progress / completed / skipped
    summary: str = ""    # 任务总结
    sources_summary: str = "" # 来源列表
    notices: list = []   # 系统提示
    note_id: str = None  # 关联笔记 ID
    note_path: str = None
```

### SummaryState
```python
@dataclass
class SummaryState:
    research_topic: str
    web_research_results: list = []  # ← Annotated with operator.add (合并用)
    sources_gathered: list = []      # ← Annotated with operator.add
    research_loop_count: int = 0
    todo_items: list = []            # ← Annotated with operator.add
    running_summary: str = ""
    structured_report: str = ""
```

---

## 8. Prompt 层：prompts.py

**文件位置**：`backend/src/prompts.py`
**职责**：定义三个 Agent 角色的 system prompt 和指令模板。

### todo_planner_system_prompt（规划专家）
告知 LLM：你是研究规划专家，把复杂主题拆成 3~5 个互补的待办任务。必须调用 note 工具同步任务信息。

### task_summarizer_instructions（总结专家）
告知 LLM：你是研究执行专家，基于搜索上下文生成 3~5 条关键发现。每条标注来源编号 `[1][2]`。

### report_writer_instructions（报告专家）
告知 LLM：你是分析报告撰写者，按模板生成结构化报告（背景概览、核心洞见、证据数据、风险挑战、参考来源）。

---

## 9. 工具层：utils.py

**文件位置**：`backend/src/utils.py`

### strip_thinking_tokens()
移除 LLM 输出中的 `<think>...</think>` 块。Qwen 思考模型会输出这种格式。

### deduplicate_and_format_sources()
将搜索结果格式化为 LLM 可读的编号来源上下文：
```
[来源1] 标题: xxx
[来源1] URL: xxx
...
--- 引用速查 ---
[1] Title — URL
```
要求 LLM 在总结中使用 `[1]`、`[2]` 引用。

### format_sources()
返回编号引用列表，与上下文中的 `[来源N]` 编号一致：
```
[1] 华东理工大学 — https://baike.baidu.com/...
[2] AI Agent 框架 — https://github.com/...
```

---

## 10. 服务层

### 10.1 planner.py — 任务规划

**关键方法**：`plan_todo_list(state)`

调用规划 Agent，使其输出包含任务的 JSON。解析逻辑（`_extract_tasks`）：

1. 尝试提取 JSON（最标准的情况）
2. 尝试提取 `[TOOL_CALL:note:{...}]` 中的参数
3. 如果都失败，创建 fallback 单任务

### 10.2 search.py — 搜索调度

**关键方法**：`dispatch_search(query, config, loop_count)`

1. 创建 SearchTool（根据配置选择 Tavily/SerpApi/DuckDuckGo）
2. 调用 `search_tool.run()`
3. 对结果执行质量评分 + 去重
4. 宽泛查询生成子查询建议

**关键方法**：`prepare_research_context(search_result, answer_text, config, rag_query)`

1. 格式化网络搜索结果（编号来源 + 引用速查表）
2. 如果知识库不为空，查询 RAG 并合并
3. 返回完整上下文字符串

### 10.3 search_quality.py — 搜索质量

**`score_source(url)`**：按域名打分
- 5 分：`.gov`、`.edu`、`.ac`
- 4 分：arxiv、semanticscholar、Google Scholar
- 3 分：Wikipedia、百度百科、Reuters、BBC
- 2 分：GitHub、Medium、知乎
- 1 分：其他

**`deduplicate_results(results, threshold=0.75)`**：Jaccard 相似度去重。

### 10.4 summarizer.py — 任务总结

**`summarize_task(state, task, context)`**：
同步生成总结。构建 prompt → agent.run() → strip_thinking_tokens → strip_tool_calls → 返回纯文本。

**`stream_task_summary(state, task, context)`**：
流式版本。返回 `(generator, getter)` 元组。Generator 实时 yield 非 `<think>` 内容；getter 最后返回完整清理后的文本。

**`_build_prompt()`**：拼装 prompt，包含任务主题、目标、搜索上下文、note 协作指引。

### 10.5 reporter.py — 报告生成

**`generate_report(state)`**：
遍历所有已完成任务，构建 prompt（含每个任务的总结和来源）。调用报告 Agent 生成最终报告。返回清理后的 Markdown 文本。

### 10.6 notes.py — 笔记协作

**`build_note_guidance(task)`**：
为 Agent 生成调用 note 工具的指令。如果 task 已有 note_id → 生成 read + update 指令；否则生成 create 指令。

Note 的 `tags` 设包含 `deep_research` 和 `task_{id}`，方便其他 Agent 按任务检索。

### 10.7 text_processing.py — 文本清洗

**`strip_tool_calls(text)`**：移除以下内容：
1. `[TOOL_CALL:note:{...}]` 标记
2. 裸 JSON 数组 `[{...}]`（含 `"action"` 键）
3. YAML frontmatter (`---\n...\n---`)

### 10.7 text_processing.py — 文本清洗

****：移除 TOOL_CALL 标记、裸 JSON 参数块、YAML frontmatter。

### 10.7b summary_schema.py — 输出格式硬约束

****：Pydantic 模型，定义任务总结的结构（3-5 条发现，每条含标题/含义与价值/多维度拓展）。

****：无论 LLM 输出什么格式，先用正则解析出每条发现，再用 Pydantic 重建为标准 Markdown。解析失败则保留原文。这是 Prompt 约束之外的硬保障。

### 10.8 tool_events.py — 工具事件追踪

跟踪 Agent 调用工具的记录（note 创建/更新/读取）。支持：
- 事件记录：`record(payload)`
- 事件消费：`drain(state)` — 返回未发送的事件并同步 task 的 note_id
- 事件推送：`set_event_sink(callback)` — 推送到 SSE 流

**`_infer_task_id(parameters)`**：从工具参数推断 task_id：
1. 直接取 `task_id` 字段
2. 从 `tags` 中匹配 `task_(\d+)`
3. 从 `title` 中匹配 `任务\s*(\d+)`

### 10.9 pipeline.py — 管道框架

可组合的 Stage 管道（当前保留核心框架，供未来扩展）：

- `ResearchContext`：流经各 Stage 的共享状态
- `PipelineStage`（ABC）：抽象阶段，定义 `execute()` 和 `stream()`
- `ResearchPipeline`：按序执行 Stage 列表

### 10.10 skill_engine.py — 技能引擎

**Skill 格式**：YAML frontmatter + Markdown body

```yaml
---
name: deep-research
triggers: ["深入研究", "全面分析"]
pipeline: standard
constraints:
  max_search_rounds: 5
---
# 技能说明...
```

**`find_by_trigger(user_input)`**：
- 英文触发器（如 "code review"）：按空格分词，全部词出现在输入中即匹配
- 中文触发器（如 "代码审查"）：逐字匹配，所有字符出现在输入中即匹配

**`match(user_input)`**：按触发词长度降序匹配，无匹配时返回默认的 `deep-research`。

---

## 11. RAG 引擎层

### 11.1 parser.py — 文件解析

**`parse_file(file_path)`**：统一入口，根据后缀分发到具体解析器。

| 格式 | 解析器 | 库 |
|---|---|---|
| PDF | `_parse_pdf` | PyMuPDF (fitz) |
| DOCX | `_parse_docx` | python-docx |
| MD/TXT/CSV/JSON | `_parse_text` | 直接读取 |

输出统一为 `ParsedDocument(title, content, metadata, page_count)`。

### 11.2 chunker.py — 文本分块

**`recursive_chunk(text, chunk_size=512, chunk_overlap=64)`**：

分割符优先级：`\n\n` → `\n` → `。` → `.` → `？` → `！` → `；` → `，` → ` ` → 字符级

每 chunk ~512 tokens（约 1024 字符），相邻 chunk 重叠 64 tokens。

**`semantic_chunk(text)`**：段落级分块（按 `\n\n` 分割），合并短段落直到达到最小长度。

### 11.3 embedder.py — 向量嵌入

**`OllamaEmbedder`**：调用 Ollama 的 `/api/embeddings` 端点。

默认模型 `qwen3-embedding:latest`，输出 4096 维向量。

**`get_embedder()`**：单例工厂，首次调用时用 "warmup" 文本验证模型可用性。

### 11.4 store.py — 向量存储

**`VectorStore`**：ChromaDB 的薄封装。

关键方法：
- `add(ids, documents, embeddings, metadatas)` — 批量添加
- `query(query_embedding, n_results=5)` — 按余弦相似度检索
- `count()` — 返回 chunk 数量

持久化目录：`./chroma_db`（SQLite + 向量文件）

### 11.5 retriever.py — 混合检索

**`HybridRetriever.retrieve(query, top_k=5)`**：

1. 语义检索：query → Embedding → ChromaDB 向量搜索
2. 关键词检索：query → TF-IDF → 倒排索引匹配
3. RRF 融合：`score = 1/(k + rank_vector + 1) + 1/(k + rank_keyword + 1)`

**`_KeywordIndex`**：内存 TF-IDF 索引。
- TF = 词频 / 文档长度
- IDF = log((N+1)/(DF+1)) + 1

### 11.6 ingest.py — 摄入管道

**`ingest_file(file_path)`**：一键完成 parse → chunk → embed → store。

返回摄入的 chunk 数量。失败返回 0。

---

## 12. 记忆层：memory/store.py

### MemoryStore（SQLite）

三张表：
- `sessions`：id, topic, report_markdown, created_at, metadata(JSON)
- `preferences`：key, value, updated_at
- `faqs`：id, question, answer, count, created_at

### SemanticMemory（ChromaDB）

知识卡片：每次研究完成后可选生成一个摘要卡片，Embedding 后存入 `semantic_memory` collection。

### check_similar_topic(topic)

新话题 → Embedding → 搜索语义记忆 → 返回相似度 > 0.8 的历史卡片。

---

## 13. 入口层：main.py

### API 端点总览

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/healthz` | 健康检查 |
| POST | `/research` | 同步研究 |
| POST | `/research/stream` | **流式研究（SSE，主要使用）** |
| GET | `/skills` | 列出所有 Skill |
| POST | `/skills/reload` | 热重载 Skill |
| POST | `/knowledge/upload` | 上传知识库文件 |
| GET | `/knowledge/stats` | 知识库统计 |
| GET | `/memory/history` | 研究历史列表 |
| GET | `/memory/history/{id}` | 单条历史详情 |
| DELETE | `/memory/history/{id}` | 删除历史 |
| GET | `/memory/preferences` | 用户偏好 |
| POST | `/memory/preferences` | 设置偏好 |
| GET | `/memory/faqs` | FAQ 列表 |
| POST | `/memory/check-topic` | 相似话题检测 |

### 启动流程

```python
app = create_app()
# on_event("startup"):
#   1. 加载 Configuration
#   2. 初始化 SkillEngine → 扫描 skills/ 目录
#   3. 打印配置摘要
```

### Windows GBK 修复

```python
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
```

---

## 14. 前端层：App.vue

**文件位置**：`frontend/src/App.vue`
**约 900 行** Vue 3 单文件组件（Template + Script + Style）

### 两大状态

**初始态**（`isExpanded = false`）：
- Hero 标题 + 输入框 + 搜索引擎选择 + 开始按钮
- 知识库上传区
- 研究历史列表（可点击展开）

**研究态**（`isExpanded = true`）：
- 左侧边栏：任务清单（可切换）+ 进度条 + 新研究按钮
- 右侧主区域：SSE 实时日志 + 任务详情（来源 + 总结 + 工具调用）+ 最终报告

### 关键事件处理

| SSE 事件类型 | 前端响应 |
|---|---|
| `skill` | 显示匹配的技能名 |
| `todo_list` | 创建任务清单 |
| `task_status` | 更新任务状态、总结、来源 |
| `task_summary_chunk` | 追加流式文本到 `task.summary` |
| `sources` | 更新来源列表 |
| `tool_call` | 记录工具调用日志 |
| `final_report` | 显示最终报告 |
| `error` | 显示错误消息 |

### 流式渲染

```
task_summary_chunk 事件 → task.summary += chunk → currentTaskSummary (computed) → v-html="renderMd(...)"
```

`renderMd()` 使用 markdown-it 将 Markdown 转为 HTML。

---

## 15. Skill 定义文件

**位置**：`backend/skills/*.skill.md`

| Skill | 触发词 | pipeline | 说明 |
|---|---|---|---|
| deep-research | 深入研究/全面分析/研究 | standard | 默认，多轮搜索 |
| quick-lookup | 快速查询/是什么/简答 | quick | 单轮搜索 |
| fact-check | 验证/真假/辟谣 | deep | 多源交叉验证 |
| code-analysis | 代码审查/review | standard | 代码审查 |
| academic-review | 文献综述/学术/论文 | deep | 学术调研 |
| sensitive-guard | (自动触发) | standard | 安全护栏 |

---

## 16. 依赖关系图

```
main.py
  ├── config.py (独立)
  ├── agent.py
  │     ├── config.py
  │     ├── models.py (独立)
  │     ├── prompts.py (独立)
  │     ├── services/planner.py
  │     │     └── models, config, prompts, utils
  │     ├── services/search.py
  │     │     ├── config, utils
  │     │     └── services/search_quality.py (独立)
  │     ├── services/summarizer.py
  │     │     └── models, config, utils, notes, text_processing
  │     ├── services/reporter.py
  │     │     └── models, config, utils, text_processing
  │     ├── services/tool_events.py
  │     │     └── models
  │     ├── services/pipeline.py
  │     │     └── models
  │     └── memory/store.py
  │           └── rag/store.py, rag/embedder.py (lazy)
  ├── services/skill_engine.py (独立 + yaml)
  ├── rag/
  │     ├── parser.py (PyMuPDF, python-docx)
  │     ├── chunker.py (独立)
  │     ├── embedder.py (requests → Ollama)
  │     ├── store.py (chromadb)
  │     ├── retriever.py → embedder + store
  │     └── ingest.py → parser + chunker + embedder + store
  └── memory/store.py → rag (lazy)
```

**"独立"** 表示该文件不 import 项目内其他文件（只依赖第三方库）。
