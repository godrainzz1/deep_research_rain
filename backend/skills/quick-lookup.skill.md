---
name: quick-lookup
version: "1.0"
description: 单轮快速查询，适用于简单事实性问题，30 秒内出结果
triggers:
  - "快速查询"
  - "快速了解"
  - "简答"
  - "是什么"
  - "查一下"
tools:
  - search
pipeline: quick
output:
  format: markdown
  sections:
    - answer
    - sources
constraints:
  max_search_rounds: 1
  require_citations: true
  max_output_tokens: 500
---
# 快速查询 Skill

## 执行流程

1. **直接搜索** — 不拆解子任务，用原始问题直接搜索
2. **简洁总结** — 一段话回答问题 + 关键事实
3. **来源标注** — 列出 2-3 个主要来源

## 输出规范

- 先给出**一句话核心答案**（加粗）
- 然后 2-3 句补充说明
- 末尾列出来源链接

## 适用场景

- "XXX 是什么？"
- "XXX 的最新动态"
- 简单的定义、数据查询
