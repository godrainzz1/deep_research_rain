"""Service that consolidates task results into the final report."""

from __future__ import annotations

import json, re

from hello_agents import ToolAwareSimpleAgent

from models import SummaryState
from config import Configuration
from utils import strip_thinking_tokens
from services.text_processing import strip_tool_calls


# 报告级别去重：如果 LLM 重复输出了研究报告标题，只保留最后一份完整报告
_REPORT_HEADING = re.compile(r"^(?:#{1,3}\s*)?(?:研究报告|最终报告|分析报告)", re.MULTILINE)


def _dedup_report(text: str) -> str:
    """Keep only the last report heading block, discarding earlier duplicates."""
    if not text:
        return text
    matches = list(_REPORT_HEADING.finditer(text))
    if len(matches) >= 2:
        text = text[matches[-1].start():].strip()
    return text


class ReportingService:
    """Generates the final structured report."""

    def __init__(self, report_agent: ToolAwareSimpleAgent, config: Configuration) -> None:
        self._agent = report_agent
        self._config = config

    def generate_report(self, state: SummaryState) -> str:
        """Generate a structured report based on completed tasks."""

        tasks_block = []
        for task in state.todo_items:
            summary_block = task.summary or "暂无可用信息"
            sources_block = task.sources_summary or "暂无来源"
            tasks_block.append(
                f"### 任务 {task.id}: {task.title}\n"
                f"- 任务目标：{task.intent}\n"
                f"- 检索查询：{task.query}\n"
                f"- 执行状态：{task.status}\n"
                f"- 任务总结：\n{summary_block}\n"
                f"- 来源概览：\n{sources_block}\n"
            )

        create_conclusion_template = json.dumps(
            {
                "action": "create",
                "title": f"研究报告：{state.research_topic}",
                "note_type": "conclusion",
                "tags": ["deep_research", "report"],
                "content": "请在此沉淀最终报告要点",
            },
            ensure_ascii=False,
        )

        prompt = (
            f"研究主题：{state.research_topic}\n\n"
            f"以下已包含全部 {len(state.todo_items)} 项子任务的完整总结与来源信息，"
            f"你无需再读取笔记，所有所需信息均已列在下方：\n\n"
            f"{''.join(tasks_block)}\n"
            f"请基于以上全部任务信息，整合撰写**一份**统一的研究报告"
            f"（不要为每个任务单独生成报告，禁止重复输出研究报告标题）。\n"
            f"如需保存最终报告要点，可调用：[TOOL_CALL:note:{create_conclusion_template}]。"
        )

        response = self._agent.run(prompt)
        self._agent.clear_history()

        report_text = response.strip()
        if self._config.strip_thinking_tokens:
            report_text = strip_thinking_tokens(report_text)

        report_text = strip_tool_calls(report_text).strip()

        # 后置去重：如果 LLM 仍然重复输出了报告标题，只保留最后一份
        report_text = _dedup_report(report_text)

        return report_text or "报告生成失败，请检查输入。"
