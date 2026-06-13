---
name: code-analysis
version: "1.0"
description: 结构化代码审查，输出架构评估、Bug 检测、优化建议
triggers:
  - "代码审查"
  - "代码分析"
  - "review"
  - "code review"
  - "审查代码"
tools:
  - search
  - note
pipeline: standard
output:
  format: markdown
  sections:
    - overview
    - architecture
    - bugs
    - performance
    - security
    - recommendations
constraints:
  require_citations: false
---
# 代码分析 Skill

## 执行流程

1. **架构理解** — 分析代码结构和设计模式
2. **Bug 检测** — 逻辑错误、边界条件、异常处理
3. **性能分析** — 时间复杂度、内存使用、IO 瓶颈
4. **安全审查** — SQL 注入、XSS、密钥泄露、权限问题
5. **改进建议** — 代码质量、可维护性、测试覆盖

## 输出规范

- 每个发现标注严重程度：🔴 严重 / 🟡 警告 / 🔵 建议
- Bug 发现附修复代码片段
- 安全漏洞附 CWE 编号（如适用）
- 优化建议标注预期收益（性能提升 X%）

## 适用场景

- PR Review
- 遗留代码重构评估
- 开源项目安全审计
