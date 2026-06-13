# DeepResearch — 全栈 AI 研究助手

基于 HelloAgents 框架的全栈深度研究助手。多轮网络搜索 + 本地知识库 RAG + 三层记忆 + Skill 插件系统。

![Backend](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)
![LLM](https://img.shields.io/badge/LLM-Qwen3.6-6366f1)
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

---

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- Ollama (可选，用于本地 LLM 降级 / Embedding / 模型)

### 1. 后端

```bash
cd backend
cp .env.example .env          # 编辑 .env 填入配置
pip install -e .
python -m uvicorn src.main:app --reload --port 8000
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

### 3. 配置环境变量

API Key 建议在**系统环境变量**中设置，`.env` 已被 gitignore 排除不会上传：

```bash
# 主 LLM
DASHSCOPE_API_KEY=sk-xxxxx

# 搜索 (至少配一个)
TAVILY_API_KEY=tvly-xxxxx
SERPAPI_API_KEY=xxxxx

# 本地 Ollama (可选)
# LLM_FALLBACK_PROVIDER=ollama
# LLM_FALLBACK_MODEL_ID=llama3:latest
```

`.env` 文件中的其他可配项见 `backend/.env.example`。

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
