---
name: fact-check
version: "1.0"
description: 交叉验证，对给定陈述进行多方来源核实，输出可信度评级
triggers:
  - "验证"
  - "真假"
  - "辟谣"
  - "事实核查"
  - "是真的吗"
  - "fact check"
  - "fake news"
  - "谣言"
tools:
  - search
  - note
pipeline: deep
output:
  format: markdown
  sections:
    - claim
    - verdict
    - evidence_for
    - evidence_against
    - confidence
    - sources
constraints:
  min_sources: 3
  require_citations: true
  cross_verify: true
---
# 事实核查 Skill

## 执行流程

1. **提取主张** — 明确待验证的具体陈述
2. **多源搜索** — 至少 3 个独立来源，优先权威机构
3. **正反证据** — 同时收集支持和反对的证据
4. **可信度评级** — 给出 真实 / 部分真实 / 无法验证 / 虚假 的判定

## 输出规范

- 标题：待验证的主张原文
- 判定结果：加粗大字，配颜色标记
- 支持证据 + 反对证据 分开列出
- 每项证据标注来源和时效性
- 最终置信度百分比

## 安全约束

- 无法验证时不强行判定
- 标注信息来源的权威性等级
