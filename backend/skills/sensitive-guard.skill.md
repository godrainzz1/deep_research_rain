---
name: sensitive-guard
version: "1.0"
description: 敏感话题安全护栏——自动检测并约束输出，确保合规
triggers: []
tools: []
pipeline: standard
output:
  format: markdown
  sections:
    - risk_assessment
    - response
constraints:
  auto_trigger: true
  block_categories:
    - illegal_content
    - self_harm
    - hate_speech
    - misinformation_campaign
    - personal_data_leak
  warn_categories:
    - medical_advice
    - legal_advice
    - financial_advice
    - political_sensitive
---
# 敏感话题安全护栏 Skill

## 自动触发机制

此 Skill 不通过用户关键词触发，而是在每次研究执行前**自动运行**。
当检测到研究主题或搜索内容命中以下类别时，自动介入。

## 阻断类别（直接拒绝）

以下类别的研究请求将直接被拒绝：
- **违法内容**：制作、传播违法工具或教程
- **自伤自杀**：鼓励或指导自伤行为
- **仇恨言论**：针对特定群体的攻击、歧视
- **虚假信息战**：批量生成虚假新闻、谣言
- **个人隐私泄露**：人肉搜索、数据泄露

## 警告类别（附免责声明后继续）

- **医疗建议** → 追加："以下内容不构成医疗建议，请咨询专业医师"
- **法律建议** → 追加："以下内容不构成法律意见，请咨询执业律师"
- **金融建议** → 追加："以下内容不构成投资建议，投资有风险"
- **政治敏感** → 保持客观中立，只陈述事实不表达立场

## 输出规范

- 阻断时：简短说明原因，不展开讨论
- 警告时：先出免责声明，再出研究内容
