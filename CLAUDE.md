# DeepResearch — 全栈 AI 研究助手

## 项目概述

基于 HelloAgents 框架的全栈深度研究助手，支持多轮网络搜索、RAG 本地知识库、三层记忆架构、Skill 插件系统。

### 技术栈
- **后端**: FastAPI + SSE 流式 · HelloAgents · ChromaDB · SQLite
- **前端**: Vue 3 + TypeScript · 暗黑科技风 · 玻璃拟态
- **LLM**: DashScope (qwen3.6-max-preview) + Ollama 本地降级
- **Embedding**: qwen3-embedding (Ollama 本地)
- **搜索**: Tavily / SerpApi / DuckDuckGo 混合

### 架构分层
```
前端 (Vue 3 暗黑风)
  ↕ SSE
FastAPI 网关 (/research/stream, /memory, /knowledge, /skills)
  ↕
Agent 编排层 (Planner → Executor → Reporter · SkillEngine)
  ↕
引擎层: Search | RAG (ChromaDB) | Memory (SQLite+Vec) | LLM (DashScope→Ollama)
```

---

## 实现流程 (20 步)

依赖关系: A→B 表示 B 依赖 A 先完成

```
Step  1: CLAUDE.md + README           [独立]
Step  2: 设计系统 (Task 15)            [独立]
Step  3: 管道重构 (Task 1)             [独立]
Step  4: SkillEngine (Task 13)         [→ Step 3]
Step  5: 内置 Skills (Task 14)         [→ Step 4]
Step  6: 搜索质量 (Task 2)             [独立]
Step  7: 引用溯源 (Task 3)             [独立]
Step  8: 文件解析器 (Task 4)           [独立]
Step  9: Chunk+Embed+ChromaDB (Task 5) [→ Step 8]
Step 10: 混合检索 (Task 6)             [→ Step 9]
Step 11: 统一检索 (Task 8)             [→ Step 10]
Step 12: 前端全新布局 (Task 16)         [→ Step 2]
Step 13: Markdown渲染 (Task 17)        [→ Step 12]
Step 14: SQLite记忆 (Task 9)           [独立]
Step 15: 语义记忆 (Task 10)            [→ Step 9, Step 14]
Step 16: 话题检测 (Task 11)            [→ Step 15]
Step 17: 记忆API+面板 (Task 12)        [→ Step 15, Step 12]
Step 18: KB上传界面 (Task 7)           [→ Step 12]
Step 19: KB管理界面 (Task 18)          [→ Step 18]
Step 20: 历史面板 (Task 19)             [→ Step 17, Step 12]
```

---

## 详细任务清单

### Step 1 — CLAUDE.md + README (Task 20)

**目标**: 保存上下文，文档化项目架构

- [ ] 创建 `CLAUDE.md`（当前文件）
- [ ] 创建 `README.md`：项目介绍、快速开始、架构图、配置说明
- [ ] 创建 `backend/.env.example`：完整的配置模板（已完成）

### Step 2 — 设计系统 (Task 15)

**目标**: 定义 CSS 变量和暗黑主题 Token，后续所有前端任务共用

- [ ] 创建 `frontend/src/styles/tokens.css`：颜色、字体、间距、圆角、阴影
- [ ] 暗黑主题调色板：深空蓝黑背景 + 青紫渐变 + 微光边框
- [ ] 玻璃拟态卡片样式 `.glass-card`
- [ ] 通用动画：流式淡入、脉冲发光、粒子浮动
- [ ] 在 `main.ts` 全局引入

### Step 3 — 管道重构 (Task 1)

**目标**: 将硬编码的 3 步管道改为可配置 Stage 组合

- [ ] 定义 `ResearchStage` 协议（抽象基类）
- [ ] 实现 `PlanStage`, `SearchStage`, `SummarizeStage`, `ReportStage`
- [ ] 实现 `ResearchPipeline` 编排器，按配置顺序执行 stages
- [ ] 支持快速/标准/深度三种预设
- [ ] Stage 间通过 `ResearchContext` 传递状态
- [ ] 每个 Stage 独立的超时、重试、fallback

### Step 4 — SkillEngine (Task 13)

**目标**: YAML+MD 解析 + 热加载 + 注册表

- [ ] 定义 Skill 格式规范：YAML frontmatter + Markdown body
- [ ] 实现 `SkillLoader`：扫描 `skills/` 目录，解析 YAML+MD
- [ ] 实现 `SkillRegistry`：按 name/trigger 检索
- [ ] 实现 `SkillExecutor`：将 skill 的 pipeline 映射到 ResearchPipeline
- [ ] FastAPI 端点：`GET /skills` 列出所有 skill

### Step 5 — 内置 Skills (Task 14)

**目标**: 创建 6 个 skill 文件

- [ ] `skills/deep-research.skill.md` — 多轮深度研究
- [ ] `skills/quick-lookup.skill.md` — 单轮快速查询
- [ ] `skills/fact-check.skill.md` — 交叉验证
- [ ] `skills/code-analysis.skill.md` — 代码审查
- [ ] `skills/academic-review.skill.md` — 学术文献综述
- [ ] `skills/sensitive-guard.skill.md` — 敏感话题检测 + 安全约束

### Step 6 — 搜索质量 (Task 2)

**目标**: 查询改写 + 来源评分 + 语义去重

- [ ] 查询改写：宽泛查询 → LLM 拆分为 2-3 个子查询
- [ ] 来源可信度评分：域名规则 + 可扩展评分表
- [ ] 语义去重：用 Embedding 计算相似度，>0.9 合并

### Step 7 — 引用溯源 (Task 3)

**目标**: 内联引用标记 + 前端 hover 卡片

- [ ] 总结 Prompt 增加 `[source_id]` 引用要求
- [ ] 报告阶段渲染引用编号与来源的映射表
- [ ] 前端 hover 来源编号显示摘要卡片

### Step 8 — 文件解析器 (Task 4)

**目标**: 支持 PDF/MD/TXT/DOCX 多格式解析

- [ ] `rag/parser.py`：统一解析接口
- [ ] PDF: PyMuPDF (fitz)
- [ ] DOCX: python-docx
- [ ] MD/TXT: 直接读取 + 元数据提取
- [ ] 输出统一格式：`{title, content, metadata, page_count}`

### Step 9 — Chunk + Embed + ChromaDB (Task 5)

**目标**: 核心 RAG 存储管线

- [ ] `rag/chunker.py`：递归分块 (512 tokens, overlap 64)
- [ ] `rag/embedder.py`：调用 qwen3-embedding (Ollama)
- [ ] `rag/store.py`：ChromaDB 封装，collection 管理
- [ ] `rag/ingest.py`：一键摄入：解析→分块→Embed→存储

### Step 10 — 混合检索 (Task 6)

**目标**: 语义 + 关键词 + Rerank

- [ ] `rag/retriever.py`：语义搜索 (ChromaDB query)
- [ ] 关键词搜索 (BM25 或简单 TF-IDF)
- [ ] 混合融合 (RRF: Reciprocal Rank Fusion)
- [ ] 可选：BGE-Reranker 重排序

### Step 11 — 统一检索 (Task 8)

**目标**: 研究时同时检索网络 + 本地知识库

- [ ] 修改 SearchStage，并行查询网络搜索 + RAG 检索
- [ ] 结果融合：标注来源类型 (web/local)
- [ ] 上下文注入 Prompt 时区分两种来源

### Step 12 — 前端全新布局 (Task 16)

**目标**: 用设计系统重写 App.vue

- [ ] 侧边栏：研究模式选择、知识库状态、历史记录入口
- [ ] 主区域：输入卡片 → 任务进度 (进度条) → 流式输出 → 最终报告
- [ ] 响应式适配：移动端折叠侧边栏
- [ ] 粒子/网格背景效果

### Step 13 — Markdown 渲染 (Task 17)

**目标**: 富文本报告 + 内联引用

- [ ] 引入 `markdown-it` + `highlight.js`
- [ ] 自定义插件：`[1]` → 可点击引用链接
- [ ] 引用 hover 弹出来源摘要卡片
- [ ] 代码块语法高亮

### Step 14 — SQLite 记忆 (Task 9)

**目标**: 研究历史 + 用户偏好持久化

- [ ] `memory/store.py`：SQLite 表设计 (sessions, preferences, faqs)
- [ ] `memory/history.py`：保存/加载研究记录
- [ ] `memory/preferences.py`：读/写用户偏好
- [ ] FastAPI 端点：`GET /memory/history`, `GET /memory/preferences`

### Step 15 — 语义记忆 (Task 10)

**目标**: 向量化知识卡片

- [ ] 每次研究完成后，自动生成"知识卡片"摘要
- [ ] 知识卡片 Embed → ChromaDB (独立 collection)
- [ ] 新研究开始时，语义搜索相似历史卡片

### Step 16 — 话题检测 (Task 11)

**目标**: 相似话题自动提醒

- [ ] 新话题 Embed → 搜索语义记忆
- [ ] 相似度 > 0.8 → 返回历史研究摘要
- [ ] 前端提示："你 N 天前研究过类似话题，是否参考？"

### Step 17 — 记忆 API + 面板 (Task 12)

**目标**: 前端可管理记忆

- [ ] FastAPI：`DELETE /memory/{id}`, `POST /memory/search`
- [ ] 前端侧边栏添加"历史记录"折叠面板
- [ ] 可搜索、删除历史记录

### Step 18 — KB 上传界面 (Task 7)

**目标**: 拖拽上传知识库文件

- [ ] 前端拖拽区域 + 文件选择按钮
- [ ] FastAPI：`POST /knowledge/upload` (multipart)
- [ ] 上传后自动触发摄入管道
- [ ] 上传进度 + 结果反馈

### Step 19 — KB 管理界面 (Task 18)

**目标**: 查看/删除已入库文件

- [ ] FastAPI：`GET /knowledge/files`, `DELETE /knowledge/{id}`
- [ ] 前端文件列表：文件名、大小、分块数、入库时间
- [ ] 删除按钮 + 确认对话框

### Step 20 — 历史面板 (Task 19)

**目标**: 前端可浏览/回看历史研究

- [ ] 侧边栏历史列表：标题 + 日期 + 标签
- [ ] 点击展开历史研究报告
- [ ] "重新研究"按钮：用相同话题再次运行

---

## 当前状态 (2026-06-13)

### 已完成
- ✅ 多 Provider LLM 支持 (DashScope + Ollama 降级)
- ✅ FallbackLLM 熔断机制
- ✅ 流式思考模型兼容 (空 choices 守卫 + max_tokens)
- ✅ 混合搜索 (Tavily/SerpApi/DuckDuckGo)
- ✅ 结构化笔记 (NoteTool)
- ✅ SSE 流式 API + 基础前端
- ✅ `.gitignore` + `.env.example`
- ✅ Step 1: CLAUDE.md + README.md
- ✅ Step 2: 设计系统 tokens.css (暗黑主题·玻璃拟态·青紫渐变)
- ✅ Step 4: SkillEngine — YAML+MD 解析 + 触发词匹配 + 热加载
- ✅ Step 6: 搜索质量 — 查询改写 + 来源评分 + 语义去重
- ✅ Step 7: 引用溯源 — 来源编号 + 引用速查表 + prompt 要求内联引用
- ✅ Step 8: 文件解析器 — PDF/DOCX/MD/TXT (PyMuPDF + python-docx)
- ✅ Step 9: Chunk+Embed+ChromaDB — 递归分块 + qwen3-embedding(4096d) + 向量存储
- ✅ Step 10: 混合检索 — 语义 + TF-IDF 关键词 + RRF 融合
- ✅ Step 11: 统一检索 — RAG 本地知识库 + 网络搜索合并上下文
- ✅ Steps 12-20: 前端暗黑主题 + Markdown渲染 + SQLite记忆 + 语义记忆 + API
- ✅ Steps 14-17: Memory系统 — SQLite(会话/偏好/FAQ) + ChromaDB语义记忆 + 话题检测

### 项目状态
全部 20 步改造完成。前后端构建通过，所有测试通过。
