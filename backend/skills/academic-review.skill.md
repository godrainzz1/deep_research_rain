---
name: academic-review
version: "1.0"
description: 学术文献综述，严格引用格式，适合论文 Related Work 撰写
triggers:
  - "文献综述"
  - "学术"
  - "论文"
  - "related work"
  - "学术调研"
tools:
  - search
  - note
pipeline: deep
output:
  format: markdown
  sections:
    - abstract
    - taxonomy
    - methods
    - gaps
    - references
constraints:
  min_sources: 8
  require_citations: true
  citation_style: "APA"
---
# 学术文献综述 Skill

## 执行流程

1. **领域扫描** — 搜索近 3-5 年顶会/顶刊论文
2. **分类梳理** — 按方法/问题/数据集建立分类体系
3. **对比分析** — 关键工作的 SOTA 对比
4. **空白识别** — 指出当前研究缺口和未来方向

## 输出规范

- 使用学术写作风格（第三人称、客观语气）
- 引用格式：作者 (年份) 或 [编号]
- 每个子领域附代表性论文 3-5 篇
- 末尾列出完整参考文献

## 数据库优先级

1. arxiv.org / semanticscholar.org
2. 顶会官网 (NeurIPS/ICML/ACL/CVPR 等)
3. Google Scholar
