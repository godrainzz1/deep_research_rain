# DeepResearch 面试问答手册

> 按面试深度分层：基础认知 → 代码细节 → 架构决策 → 场景设计。
> 每道题附参考答案。字节风格面试题标注 ⭐。

---

## 目录

- [一、项目整体认知](#一项目整体认知)
- [二、Agent 架构与管道](#二agent-架构与管道)
- [三、LLM 调用与降级](#三llm-调用与降级)
- [四、搜索与 RAG](#四搜索与-rag)
- [五、记忆系统](#五记忆系统)
- [六、Skill 系统](#六skill-系统)
- [七、SSE 流式推送](#七sse-流式推送)
- [八、FastAPI 与工程实践](#八fastapi-与工程实践)
- [九、场景设计题](#九场景设计题)
- [十、快速自查清单](#十快速自查清单)

---

## 一、项目整体认知

### Q1：用一句话介绍你的项目

> DeepResearch 是一个输入话题、自动产出研究报告的 AI 助手。核心技术栈是 FastAPI + ChromaDB + SQLite + Ollama，Agent 管道自动完成话题拆解→多源搜索→逐任务总结→生成带引用的结构化报告，全程 SSE 流式推送到前端。

### Q2：项目的核心数据流是怎样的？

> 用户输入话题 → Agent 拆解为 3~5 个子任务 → 每个子任务独立搜索+总结 → 汇总生成报告。
>
> 具体来说：`POST /research/stream` → `agent.run_stream()` → `planner.plan_todo_list()`（LLM 拆任务）→ 每个任务开线程执行 `_execute_task()`（搜索→总结）→ `reporter.generate_report()`（LLM 出报告）→ SSE 推送每一步结果。

### Q3：这个项目有哪些模块？各负责什么？

> - **agent.py**：总控，协调 Planner/Executor/Reporter
> - **planner.py**：调 LLM 拆解话题为子任务
> - **search.py**：搜索调度（Tavily/SerpApi/DuckDuckGo）
> - **search_quality.py**：来源评分、去重、查询改写
> - **summarizer.py**：逐任务流式总结
> - **reporter.py**：汇总生成最终报告
> - **pipeline.py**：可组合的 Stage 管道框架
> - **skill_engine.py**：YAML+MD 技能插件系统
> - **rag/**：文件解析→分块→Embedding→ChromaDB→混合检索
> - **memory/store.py**：SQLite 历史 + 偏好 + ChromaDB 语义记忆
> - **main.py**：FastAPI 入口，暴露 REST API + SSE

### Q4：你在这个项目中的角色是什么？

> 我是项目的架构设计者和主要开发者。基础原型来自 GitHub 上的一个 Agent 教程 Demo（约 500 行），我在此基础上重构了架构，新增了 RAG 引擎、记忆系统、Skill 插件、搜索质量增强、LLM 降级机制等模块，扩展到 9000+ 行。开发过程中全程使用 Claude Code 作为 AI 编程助手，我负责架构决策、需求定义和 Bug 调试，代码生成由 AI 辅助完成。

---

## 二、Agent 架构与管道

### Q5：Agent 的三阶段管道是怎样的？ ⭐

> Planner → Executor → Reporter。
>
> **Planner**（研究规划专家）：接收话题，输出 3~5 个 TodoItem（含标题、意图、检索查询词）。
> **Executor**（任务总结专家）：对每个 TodoItem，先搜索网络，再基于搜索结果生成 3~5 条关键发现。
> **Reporter**（报告撰写专家）：汇总所有已完成任务的总结和来源，生成结构化最终报告。
>
> 每个阶段是独立的 Agent 实例，有各自的 system prompt 和工具权限。

### Q6：为什么用三个独立的 Agent 而不是一个大 Agent 全做完？

> 拆成三个 Agent 的好处：
> 1. **Prompt 解耦**：规划需要 JSON 输出、总结需要 Markdown、报告需要结构化模板——不同任务的 prompt 差异很大，拆开写更清晰
> 2. **错误隔离**：某个 Agent 的 LLM 调用失败不会影响其他阶段
> 3. **可替换性**：可以单独优化某个 Agent（比如换个更强的模型做规划）

### Q7：Planner 输出的 JSON 如果格式不对怎么办？ ⭐

> `planner.py` 的 `_extract_tasks()` 方法有三层容错：
> 1. 先尝试标准 JSON 解析（`_extract_json_payload`）
> 2. 失败则尝试从 `[TOOL_CALL:note:{...}]` 中提取任务信息
> 3. 都失败则调用 `create_fallback_task()` 创建一个兜底的"基础背景梳理"任务
>
> 这样即使 LLM 输出格式异常，研究流程也不会中断。

### Q8：_execute_task 中的流式逻辑是怎样的？ ⭐

> 关键代码在 `agent.py` 的 `_execute_task()` 方法。当 `emit_stream=True` 时：
> 1. 先 yield `task_status: in_progress`
> 2. 调用 `dispatch_search()` 搜索
> 3. 如果有搜索结果 → yield `sources` 事件 → 调用 `summarizer.stream_task_summary()` → 逐块 yield `task_summary_chunk`
> 4. 最后 yield `task_status: completed`
> 5. 中间穿插 `_drain_tool_events()` 推送工具调用记录
>
> 如果搜索无结果 → yield `task_status: skipped`

---

## 三、LLM 调用与降级

### Q9：FallbackLLM 的工作原理是什么？ ⭐

> 一个透明代理，包装 primary（主 LLM）和 fallback（备 LLM）。
>
> 第一次调用 primary，如果失败 → 设置 `_primary_dead = True` → 改为调用 fallback → 后续所有调用直接走 fallback，不再重试 primary。
>
> 关键是用 `__getattr__` 将所有属性访问委托给 primary，所以下游代码完全不知道降级发生了。

### Q10：为什么用熔断（circuit breaker）而不是每次重试？

> 如果 primary 因为 API 余额耗尽返回 403，每次重试浪费 1~2 秒 HTTP 往返，且产生无效请求。一次判断后全部直走 fallback，减少延迟和错误日志噪音。

### Q11：如果 fallback 也失败了怎么办？

> `FallbackLLM.invoke()` 的 fallback 调用也包了 try/except。如果 fallback 也失败，返回空字符串 `""`，Agent 继续执行（报告可能为空，但不会崩溃）。`stream_invoke()` 同理，记录错误日志后停止迭代。

### Q12：怎么切换不同的 LLM 提供商？ ⭐

> 通过 `config.py` 的 `_auto_detect_provider()` 自动检测：
> - 有 `DASHSCOPE_API_KEY` → qwen 提供商
> - 有 `OPENAI_API_KEY` → openai 提供商
> - base_url 包含 `localhost:11434` → ollama
> - base_url 包含 `dashscope.aliyuncs.com` → qwen
>
> 也可以在 `.env` 中显式设置 `LLM_PROVIDER` 覆盖自动检测。

### Q13：思考模型的 `<think>` 标签怎么处理？

> 两个层面：
> 1. **流式输出时**：`summarizer.py` 的 `stream_task_summary()` 实时过滤——遇到 `<think>` 开始缓冲，遇到 `</think>` 丢弃缓冲内容，只 yield 可见文本
> 2. **最终输出时**：`utils.strip_thinking_tokens()` 移除所有 `<think>...</think>` 块

---

## 四、搜索与 RAG

### Q14：搜索怎么知道用哪个后端？ ⭐

> `config.py` 中配置 `SEARCH_API`（默认 `hybrid`）。`dispatch_search()` 创建对应后端实例：
> - hybrid → 先试 Tavily，失败则 SerpApi，再失败则 DuckDuckGo
> - duckduckgo → 免 API Key，直接可用

### Q15：来源可信度评分是怎么实现的？

> `search_quality.py` 的 `score_source(url)` 方法。提取域名，匹配预设规则：
> - 5 分：gov、edu、ac（政府、教育）
> - 4 分：arxiv、Google Scholar（学术）
> - 3 分：Wikipedia、百度百科、BBC（权威媒体）
> - 2 分：GitHub、知乎（社区）
> - 1 分：其他
>
> 结果按分数降序排列，低分来源不会被丢弃，但展示顺序靠后。

### Q16：语义去重是怎么做的？

> Jaccard 相似度。对每个结果取标题 + 前 200 字内容，分词后计算交集/并集。相似度 > 0.75 视为重复，保留第一个。

### Q17：RAG 管道的完整流程是怎样的？ ⭐

> ```
> 上传文件 → parser.parse_file() → chunker.recursive_chunk()
>          → embedder.embed_batch() → store.add()
>          → (持久化到 ChromaDB)
>
> 研究时 → retriever.retrieve(query)
>         → 语义检索（向量）+ 关键词检索（TF-IDF）
>         → RRF 融合排序
>         → 注入 LLM 上下文
> ```

### Q18：RAG 检索到的内容怎么和网络搜索结果融合？

> `search.py` 的 `prepare_research_context()` 方法。先格式化网络搜索结果（带 `[来源N]` 编号），再检查 ChromaDB 中知识库是否为空。如果不为空，调用 `retriever.retrieve_context()` 获取最相关的 3 个文本块，标记为 `📚 本地知识库`，追加到上下文末尾。LLM 收到的就是混合的上下文。

### Q19：ChromaDB 的数据存在哪里？重启会丢吗？

> 存在 `backend/chroma_db/` 目录（SQLite + 向量数据文件）。ChromaDB 的 `PersistentClient` 保证重启后数据不丢失。这个目录已被 `.gitignore` 排除。

### Q20：为什么 Embedding 用 qwen3-embedding 而不是 OpenAI 的？

> 1. 本地免费，不走 API 不计费
> 2. 中文效果好（Qwen 系列对中文优化）
> 3. 4096 维向量，精度足够
> 4. 通过 Ollama 调用，集成简单

### Q21：混合检索中的 TF-IDF 和 RRF 是怎么实现的？ ⭐

> TF-IDF：自己写的 `_KeywordIndex` 类。TF = 词频/文档长度，IDF = log((N+1)/(DF+1)) + 1（平滑版本）。
>
> RRF（Reciprocal Rank Fusion）：`score = 1/(k + rank + 1)`，其中 k=60。把语义检索和关键词检索的排名列表按这个公式融合，得分高的排在前面。RRF 的好处是不需要训练、不需要知道原始分数的分布。

---

## 五、记忆系统

### Q22：三层记忆分别是什么？区别在哪？ ⭐

> | 层级 | 存储 | 生命周期 | 数据结构 |
> |---|---|---|---|
> | 工作记忆 | Python 内存（SummaryState） | 单次会话 | 话题、任务列表、搜索结果、报告 |
> | 情景记忆 | SQLite（memory.db） | 跨会话持久 | 研究历史、用户偏好、FAQ |
> | 语义记忆 | ChromaDB（semantic_memory collection） | 长期积累 | 知识卡片向量化，支持语义召回 |

### Q23：每次研究怎么保存到记忆？

> `agent.py` 的 `run_stream()` 方法末尾，在报告生成后调用：
> ```python
> memory_store.save_session(session_id, topic, report, metadata)
> ```
> 写入 SQLite 的 `sessions` 表。`metadata` JSON 字段存储 skill 名称和任务标题。

### Q24：相似话题检测怎么实现？

> `memory/store.py` 的 `check_similar_topic(topic)`：
> 1. 将新话题 Embedding
> 2. 在 ChromaDB 的 `semantic_memory` collection 中检索
> 3. 返回余弦相似度 > 0.8 的历史知识卡片

---

## 六、Skill 系统

### Q25：Skill 是怎么定义和加载的？ ⭐

> 每个 Skill 是一个 `.skill.md` 文件，YAML frontmatter 声明元数据，Markdown body 写执行规范。
>
> `SkillEngine.load_all()` 扫描 `skills/` 目录，用 `parse_skill_file()` 解析。前端通过 `GET /skills` 查看，`POST /skills/reload` 热重载。

### Q26：Skill 怎么匹配用户输入？

> `SkillRegistry.find_by_trigger(user_input)`：
> - 英文触发词（如 "code review"）：按空格分词，全部词出现在输入中即匹配
> - 中文触发词（如 "代码审查"）：逐字匹配，所有字出现在输入中即匹配
> - 按触发词长度降序匹配，保证更具体的先命中
>
> 用户输入"帮我审查这段代码" → "代码审查"（2 个字拆开都在输入中）→ 命中 `code-analysis`

### Q27：sensitive-guard 怎么自动触发的？

> 在 `skill_engine.py` 中，`match()` 方法对触发词列表为空的 skill 不做匹配。`sensitive-guard` 的 `triggers: []` + `constraints: auto_trigger: true`，但目前还需要在 `run_stream()` 中显式调用检测逻辑。这是一个已知的待完善点。

---

## 七、SSE 流式推送

### Q28：为什么用 SSE 而不是 WebSocket？ ⭐

> SSE 适合本项目，因为：
> 1. 单向推送（服务端→前端），研究进度不需要前端回传
> 2. 基于 HTTP，不需要额外协议升级握手
> 3. 浏览器 `EventSource` API 原生支持，自动重连
> 4. FastAPI 的 `StreamingResponse` 对 SSE 支持好
>
> WebSocket 更适合双向实时通信（聊天），这里用不上。

### Q29：SSE 事件的发送是怎么保证"线程安全"的？

> `run_stream()` 使用 Python 的 `queue.Queue`（线程安全队列）协调。每个 task 线程把事件 push 到队列，主线程以 0.2s 间隔 poll 队列，有事件立刻 yield 给 FastAPI。Queue 本身是线程安全的。

### Q30：如果网络断开，SSE 会怎样？

> 浏览器的 `EventSource` 会自动重连。服务端需要处理客户端断连——FastAPI 的 `StreamingResponse` 在客户端断开时会停止迭代生成器。

---

## 八、FastAPI 与工程实践

### Q31：FastAPI 和 Flask 的区别？为什么选 FastAPI？

> FastAPI 选型理由：
> 1. 原生异步支持（`async def`），SSE 需要异步
> 2. `StreamingResponse` 直接支持生成器作为响应体
> 3. 自动生成 OpenAPI 文档（`/docs`）
> 4. Pydantic 做请求验证（`ResearchRequest`）
>
> Flask 是同步框架，做 SSE 需要额外插件且性能不如 FastAPI。

### Q32：为什么用 `.env` + 系统环境变量双重配置？

> `.env` 存项目配置（模型名、URL），系统环境变量存敏感信息（API Key）。
> `.env` 被 `.gitignore` 排除，不会上传。
> 两级配置的优先级：系统环境变量 > `.env` 文件 > 代码默认值。

### Q33：项目中有哪些异常处理策略？

> 三层容错：
> 1. **LLM 调用**：`FallbackLLM` 自动降级，返回空字符串不崩溃
> 2. **任务规划**：`plan_todo_list()` 失败 → `create_fallback_task()` 兜底
> 3. **搜索**：hybrid 模式多后端 fallback
> 4. **报告生成**：失败返回错误消息，不影响前端展示任务结果

### Q34：如果要部署到生产环境，需要改什么？

> 1. 把 ChromaDB 和 SQLite 换成服务化方案（如 Milvus + PostgreSQL）
> 2. 加认证（API Key 或 OAuth2）
> 3. 加请求速率限制（rate limiting）
> 4. 用 Gunicorn + Uvicorn workers 替代单进程 `uvicorn --reload`
> 5. 前端 build 后用 Nginx 托管静态文件
> 6. 加日志收集和监控（Prometheus + Grafana）

---

## 九、场景设计题

### Q35：如果要支持"用户打断正在运行的研究"，怎么设计？ ⭐

> 目前已有 `AbortController` 在前端取消请求。后端需要改进：
> 1. 给 Agent 传一个 `threading.Event` 作为取消信号
> 2. `_execute_task()` 的每个阶段（搜索后、总结前）检查 `event.is_set()`
> 3. 如果已设置，yield `{"type": "cancelled"}` 并提前返回
> 4. Thread 用 `daemon=True` 确保主进程退出时自动清理

### Q36：如果要支持多用户同时使用，架构怎么改？

> 1. Agent 实例从全局单例改为请求级创建（已实现）
> 2. ChromaDB 和 SQLite 改为服务化（多个 Agent 实例不能同时写同一个 SQLite）
> 3. 知识库加用户隔离（每个用户独立 collection）
> 4. 加用户认证和会话管理
> 5. 用消息队列（Redis）替代 `queue.Queue` 实现分布式 SSE

### Q37：如果想给报告加"置信度打分"，怎么设计？

> 1. 每条结论要求 LLM 输出置信度（高/中/低）
> 2. 置信度高：3+ 来源一致支持
> 3. 置信度中：1~2 个来源支持，无矛盾
> 4. 置信度低：单一来源或来源间有矛盾
> 5. 前端用颜色标记（绿色/黄色/红色）
> 6. 可扩展为数值化评分（1~5），用来源数量和质量加权

### Q38：当前 RAG 不区分"知识库来源"和"网络来源"的优先级，怎么改进？

> 1. 在 `prepare_research_context()` 中给不同来源加标签权重
> 2. 知识库来源加 `[可信度: 高]` 标记（用户自己上传，信任度高）
> 3. 修改 prompt 要求 LLM 优先采信知识库内容
> 4. 当知识库和网络搜索结果矛盾时，明确指出并标记争议点

---

## 十、快速自查清单

面试前一天过一遍这 15 个问题，确保能流畅回答：

- [ ] 项目的核心流程：用户输入话题到出报告，经过了哪些步骤？
- [ ] `agent.py` 的 `run_stream()` 方法怎么实现流式？
- [ ] FallbackLLM 的熔断机制怎么工作？为什么不每次重试？
- [ ] `_execute_task()` 的完整流程？
- [ ] SSE 和 WebSocket 的区别？为什么选 SSE？
- [ ] RAG 从文件上传到检索的完整链路？
- [ ] ChromaDB 数据存在哪？重启会丢吗？
- [ ] Skill 怎么匹配用户输入？中英文匹配策略有何不同？
- [ ] 三层记忆的区别和存储方式？
- [ ] 搜索结果怎么评分和去重？
- [ ] Planner 输出格式错误时怎么容错？
- [ ] `.env` 和系统环境变量的优先级关系？
- [ ] 线程 + 队列模型的流式方案，为什么这么设计？
- [ ] 思考模型的 `<think>` 标签在哪两层处理？
- [ ] 如果要支持多用户，架构怎么改？

---

> 提示：面试中被要求"打开代码看看"时，最可能被点到的方法：
> 1. `agent.py` → `run_stream()`（核心流程）
> 2. `agent.py` → `_execute_task()`（单任务执行）
> 3. `agent.py` → `FallbackLLM.invoke()`（降级逻辑）
> 4. `search.py` → `prepare_research_context()`（RAG 融合）
> 5. `summarizer.py` → `stream_task_summary()`（流式总结）
> 6. `skill_engine.py` → `find_by_trigger()`（Skill 匹配）
