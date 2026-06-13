# DeepResearch — 全栈 AI 研究助手

基于 HelloAgents 框架的全栈深度研究助手。多轮网络搜索 + 本地知识库 RAG + 三层记忆 + Skill 插件系统。

![Backend](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)
![LLM](https://img.shields.io/badge/LLM-Multi_Provider-6366f1)
![Frontend](https://img.shields.io/badge/Frontend-Vue_3-4fc08d?logo=vuedotjs)
![VectorDB](https://img.shields.io/badge/VectorDB-ChromaDB-ff6b6b)
![Python](https://img.shields.io/badge/Python-3.10+-3776ab?logo=python)

---

## 架构

```
前端 (Vue 3 暗黑风)
  ↕ SSE 流式
FastAPI 网关  (/research/stream · /knowledge · /memory · /skills)
  ↕
Agent 编排层  (Planner → Executor → Reporter · SkillEngine)
  ↕
引擎层:  Search(Tavily/SerpApi) | RAG(ChromaDB) | Memory(SQLite+Vec) | LLM(DashScope→Ollama)
```

---

## 这是什么

DeepResearch 是一个**输入话题、自动产出研究报告**的 AI 助手。你只需要告诉它你想研究什么，它会：

1. **拆解话题** — 将宽泛主题拆成 3~5 个互补的子任务
2. **全网搜索** — 自动调用 Tavily / SerpApi / DuckDuckGo 检索
3. **逐任务总结** — 每个子任务独立分析，实时流式输出
4. **生成报告** — 汇总所有子任务，产出一份带引用来源的结构化报告

整个过程在网页中**实时可见**——搜索了什么、找到了哪些来源、LLM 正在写什么——而不是提交后干等。

### 典型使用场景

| 场景 | 示例 |
|---|---|
| 技术调研 | "2025 年 AI Agent 框架有哪些主流选择？" |
| 行业分析 | "中国新能源汽车在欧洲市场的前景" |
| 学术初探 | "Transformer 架构的最新变体及其应用" |
| 事实核查 | "验证'开源模型已超越 GPT-4'这个说法" |
| 产品研究 | "市面上最好的向量数据库有哪些？各有什么优劣？" |

### 使用流程

1. 打开 `http://localhost:5173`
2. 在输入框输入研究话题，选择搜索引擎，点击 **开始研究**
3. 左侧出现**任务清单**，右侧实时展示搜索来源和流式总结
4. 所有子任务完成后，底部自动生成**最终研究报告**（带引用编号）
5. 研究自动保存到**历史记录**，下次打开可回顾

如果本地有相关资料，可以**上传 PDF / Word / Markdown 文件**到知识库，研究时会自动结合本地文件一起分析。

### 项目来源

本项目原型基于 [HelloAgents 框架](https://github.com/datawhalechina/hello-agents) 的 Agent 教程 Demo，实现了 Planner-Executor-Reporter 基础流程。在此基础上进行了大幅架构扩展，核心增量贡献包括：

- **RAG 知识库引擎**：文档解析 → 分块 → Embedding → ChromaDB → 混合检索
- **三层记忆系统**：SQLite 情景记忆 + ChromaDB 语义记忆，跨会话持久化
- **Skill 插件系统**：YAML+MD 定义式，6 个内置技能，触发词匹配 + 热加载
- **搜索质量增强**：查询改写、来源可信度评分、语义去重
- **LLM 降级机制**：主模型异常时熔断切换本地 Ollama

开发全程使用 Claude Code 作为 AI 编程助手，本人负责架构设计、需求定义与缺陷调试。

---

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- Ollama (可选，用于本地 LLM 降级 / Embedding / 模型)

### 1. 安装后端依赖

```bash
cd backend
pip install -e .
```

> 如果 `pip install -e .` 报错，可以手动安装核心依赖：
> ```bash
> pip install fastapi uvicorn python-dotenv pydantic pyyaml loguru requests openai chromadb PyMuPDF python-docx
> ```

### 2. 配置环境变量

API Key **强烈建议**在系统环境变量中设置，不要写在 `.env` 文件里（已 gitignore 排除，不会上传）：

**Windows** (PowerShell 管理员模式):
```powershell
[System.Environment]::SetEnvironmentVariable('DASHSCOPE_API_KEY','sk-xxxxx','User')
[System.Environment]::SetEnvironmentVariable('TAVILY_API_KEY','tvly-xxxxx','User')
```

**macOS / Linux** (追加到 `~/.zshrc` 或 `~/.bashrc`):
```bash
export DASHSCOPE_API_KEY=sk-xxxxx
export TAVILY_API_KEY=tvly-xxxxx
```

可选配置（存放在 `backend/.env`）：
```bash
cd backend
cp .env.example .env
# 按需编辑 .env，主要是 LLM_MODEL_ID 和 LLM_BASE_URL
# API Key 不要写在这里，用上面的系统环境变量方式
```

> 需要哪些 API Key：
> | Key | 用途 | 获取地址 |
> |---|---|---|
> | `DASHSCOPE_API_KEY` | 阿里云百炼 LLM | https://bailian.console.aliyun.com |
> | `TAVILY_API_KEY` | Tavily 搜索 | https://tavily.com |
> | `SERPAPI_API_KEY` | SerpApi 搜索 (备选) | https://serpapi.com |

### 3. 启动后端

```bash
cd backend
python -m uvicorn src.main:app --reload --port 8000
```

看到以下日志说明启动成功：
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     SkillEngine loaded 6 skill(s) from skills
```

验证一下：
```bash
curl http://localhost:8000/healthz
# → {"status":"ok"}
```

### 4. 启动前端

**新开一个终端**，后端保持运行：

```bash
cd frontend
npm install
npm run dev
```

看到以下输出说明启动成功：
```
  VITE v5.x.x  ready in xxx ms
  ➜  Local:   http://localhost:5173/
```

浏览器打开 `http://localhost:5173` 即可使用。

### 5. 可选：启动 Ollama (本地模型降级)

```bash
# 安装 Ollama: https://ollama.com
ollama pull llama3:latest        # 降级兜底模型
ollama pull qwen3-embedding      # RAG Embedding 模型
```

`.env` 中启用：
```bash
LLM_FALLBACK_PROVIDER=ollama
LLM_FALLBACK_MODEL_ID=llama3:latest
OLLAMA_BASE_URL=http://localhost:11434
```

---

### 常见问题

**Q: 启动后端报 `ModuleNotFoundError: No module named 'config'`**

需要在 `backend/` 目录下运行，或设置 `PYTHONPATH`：
```bash
cd backend
PYTHONPATH=src python -m uvicorn src.main:app --port 8000
```

**Q: 前端显示"报告生成失败"**

检查后端终端日志，常见原因：
- `DASHSCOPE_API_KEY` 未设置或已过期
- API 免费额度用完 → 换模型：修改 `.env` 中 `LLM_MODEL_ID`
- 搜索 API Key 未配置 → 至少配一个 Tavily 或 SerpApi

**Q: 端口被占用**

```bash
# 后端换端口
python -m uvicorn src.main:app --reload --port 8001
# 同时修改 frontend/.env.local 中的 VITE_API_BASE_URL
```

**Q: 想用自己的 OpenAI 兼容 API**

编辑 `backend/.env`：
```bash
LLM_MODEL_ID=你的模型名
LLM_BASE_URL=https://你的API地址/v1
LLM_API_KEY=你的Key
```

---

## Skill 系统

项目内置 6 个 Skill，定义在 `backend/skills/` 目录下。每个 Skill 是一个 YAML + Markdown 文件，声明触发词、执行管道、输出规范和安全约束。

| Skill | 触发词 | 说明 |
|---|---|---|
| `deep-research` | 深入研究 / 全面分析 | 多轮搜索 + 任务拆解 + 结构化报告（默认） |
| `quick-lookup` | 快速查询 / 是什么 | 单轮搜索，30 秒内出结果 |
| `fact-check` | 验证 / 辟谣 / 真假 | 多源交叉验证，输出可信度评级 |
| `code-analysis` | 代码审查 / review | 结构化代码审查：Bug、性能、安全 |
| `academic-review` | 文献综述 / 论文 | 学术调研，APA 引用格式 |
| `sensitive-guard` | *(自动触发)* | 敏感话题检测，阻断违法/自伤/仇恨内容 |

### 如何添加新 Skill

在 `backend/skills/` 下创建 `.skill.md` 文件：

```yaml
---
name: my-skill
version: "1.0"
description: 自定义技能
triggers:
  - "我的关键词"
tools:
  - search
  - note
pipeline: standard
constraints:
  max_search_rounds: 3
---
# 技能说明 (Markdown)

执行流程和输出规范...
```

启动时自动加载，`POST /skills/reload` 热重载。

---

## Memory 系统

三层记忆架构，跨会话持久化：

| 层级 | 存储 | 生命周期 | 内容 |
|---|---|---|---|
| **工作记忆** | 内存 | 单次会话 | 当前研究上下文、对话历史 |
| **情景记忆** | SQLite (`memory.db`) | 跨会话 | 历史研究、用户偏好、FAQ |
| **语义记忆** | ChromaDB | 长期积累 | 知识卡片向量化，语义检索 |

### 使用方式

- 每次研究完成**自动保存**到情景记忆
- 首页显示**研究历史**列表，点击可展开查看完整报告
- 新研究开始时自动检测**相似话题**（语义记忆召回）
- API：`GET /memory/history` · `GET /memory/preferences` · `DELETE /memory/history/{id}`

---

## RAG 知识库

完整 RAG 管道：文件解析 → 智能分块 → Embedding → 向量存储 → 混合检索。

### 架构

```
上传文件 (PDF/DOCX/MD/TXT)
  → 解析 (PyMuPDF / python-docx)
  → 递归分块 (512 tokens, 64 overlap)
  → Embedding (qwen3-embedding, 4096d)
  → ChromaDB 向量存储
  → 研究时自动检索 + 与网络搜索结果融合
```

### 使用方式

1. 在首页点击上传 PDF/DOCX/MD/TXT 文件
2. 系统自动解析、分块、向量化
3. 开始研究时，本地知识库内容自动与网络搜索结果合并
4. 报告中标注 `📚 本地知识库` 来源

### 技术选型

| 组件 | 选型 |
|---|---|
| PDF 解析 | PyMuPDF |
| 分块 | 递归分块 (RecursiveCharacterTextSplitter) |
| Embedding | qwen3-embedding (Ollama 本地) |
| 向量库 | ChromaDB |
| 检索 | 语义 (cosine) + 关键词 (TF-IDF) + RRF 融合 |

---

## 搜索增强

- **混合后端**：Tavily / SerpApi / DuckDuckGo，自动 fallback
- **查询改写**：宽泛查询自动拆分为子查询
- **来源评分**：按域名权威性打分 (.gov > .edu > 百科 > 媒体 > 博客)
- **语义去重**：相似度 > 0.75 的结果合并
- **引用溯源**：内联 `[1][2]` 编号，前端展示对应 URL

---

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/research` | 同步研究（一次性返回） |
| POST | `/research/stream` | 流式研究（SSE，推荐） |
| GET | `/skills` | 列出所有 Skill |
| POST | `/skills/reload` | 热重载 Skill |
| POST | `/knowledge/upload` | 上传知识库文件 |
| GET | `/knowledge/stats` | 知识库统计 |
| GET | `/memory/history` | 研究历史 |
| GET | `/memory/history/{id}` | 单条历史详情 |
| DELETE | `/memory/history/{id}` | 删除历史 |
| GET | `/memory/preferences` | 用户偏好 |
| GET | `/healthz` | 健康检查 |

---

## 项目结构

```
deep-research/
├── README.md
├── CLAUDE.md
├── .gitignore
├── backend/
│   ├── .env.example                # 配置模板
│   ├── pyproject.toml
│   ├── skills/                     # Skill 定义
│   │   ├── deep-research.skill.md
│   │   ├── quick-lookup.skill.md
│   │   ├── fact-check.skill.md
│   │   ├── code-analysis.skill.md
│   │   ├── academic-review.skill.md
│   │   └── sensitive-guard.skill.md
│   └── src/
│       ├── main.py                 # FastAPI 入口
│       ├── agent.py                # Agent 编排 + FallbackLLM
│       ├── config.py               # 配置模型
│       ├── models.py               # 数据模型
│       ├── prompts.py              # System prompts
│       ├── utils.py                # 工具函数
│       ├── rag/                    # RAG 引擎
│       │   ├── parser.py           # 文件解析 (PDF/DOCX/MD)
│       │   ├── chunker.py          # 智能分块
│       │   ├── embedder.py         # Embedding (Ollama)
│       │   ├── store.py            # ChromaDB 封装
│       │   ├── retriever.py        # 混合检索
│       │   └── ingest.py           # 一键摄入管道
│       ├── memory/
│       │   └── store.py            # SQLite + 语义记忆
│       └── services/
│           ├── pipeline.py         # 研究管道 (quick/standard/deep)
│           ├── skill_engine.py     # Skill 引擎
│           ├── planner.py          # 任务规划
│           ├── search.py           # 搜索调度
│           ├── search_quality.py   # 搜索质量
│           ├── summarizer.py       # 任务总结
│           ├── reporter.py         # 报告生成
│           ├── notes.py            # 笔记协作
│           ├── text_processing.py  # 文本清洗
│           └── tool_events.py      # 工具事件追踪
└── frontend/
    └── src/
        ├── App.vue                 # 主界面
        ├── main.ts
        ├── style.css
        ├── styles/tokens.css       # 设计系统
        └── services/api.ts         # SSE 客户端
```

---

## License

MIT
