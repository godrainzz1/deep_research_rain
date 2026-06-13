---
name: deep-research
version: "1.0"
description: 多轮深度研究，适用于复杂话题的全面分析
triggers:
  - "深入研究"
  - "全面分析"
  - "深度调研"
  - "帮我调研"
  - "分析一下"
  - "研究"
tools:
  - search
  - note
pipeline: standard
output:
  format: markdown
  sections:
    - background
    - findings
    - evidence
    - risks
    - sources
constraints:
  max_search_rounds: 5
  require_citations: true
  language: auto
---
# 深度研究 Skill

## 执行流程

1. **理解意图** — 必要时反问澄清研究范围
2. **任务拆解** — 将主题拆解为 3-5 个可独立检索的子任务
3. **逐任务执行** — 每个子任务：搜索 → 提取 → 总结 → 笔记同步
4. **整合报告** — 融合各子任务结论，生成结构化最终报告

## 输出规范

- 使用 Markdown 格式，标题层级清晰
- 所有事实性陈述**必须**内联标注来源 `[ID]`
- 不确定的信息标注置信度：高 / 中 / 低
- 每个章节末尾列出关键引用来源

## 安全约束

- 拒绝生成违法、危险、侵权内容
- 医疗/法律建议必须附带免责声明
- 涉及个人隐私的信息自动脱敏
