"""Task summarization utilities."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Tuple

from hello_agents import ToolAwareSimpleAgent

from models import SummaryState, TodoItem
from config import Configuration
from utils import strip_thinking_tokens
from services.notes import build_note_guidance
from services.text_processing import strip_tool_calls
from services.summary_schema import normalize_summary


class SummarizationService:
    """Handles synchronous and streaming task summarization."""

    def __init__(
        self,
        summarizer_factory: Callable[[], ToolAwareSimpleAgent],
        config: Configuration,
    ) -> None:
        self._agent_factory = summarizer_factory
        self._config = config

    def summarize_task(self, state: SummaryState, task: TodoItem, context: str,
                       skill_body: str = "") -> str:
        """Generate a task-specific summary using the summarizer agent."""

        prompt = self._build_prompt(state, task, context, skill_body)

        agent = self._agent_factory()
        try:
            response = agent.run(prompt)
        finally:
            agent.clear_history()

        summary_text = response.strip()
        if self._config.strip_thinking_tokens:
            summary_text = strip_thinking_tokens(summary_text)

        summary_text = strip_tool_calls(summary_text).strip()

        # Deduplicate: keep only last occurrence of "任务总结" heading
        import re
        heading = re.compile(r"^(?:#{1,3}\s*)?任务总结", re.MULTILINE)
        matches = list(heading.finditer(summary_text))
        if len(matches) >= 2:
            summary_text = summary_text[matches[-1].start():].strip()

        # Pydantic schema normalization: parse → reformat for consistent output
        summary_text = normalize_summary(summary_text)

        return summary_text or "暂无可用信息"

    def stream_task_summary(
        self, state: SummaryState, task: TodoItem, context: str,
        skill_body: str = "",
    ) -> Tuple[Iterator[str], Callable[[], str]]:
        """Stream the summary text for a task while collecting full output."""

        prompt = self._build_prompt(state, task, context, skill_body)
        remove_thinking = self._config.strip_thinking_tokens
        raw_buffer = ""
        visible_output = ""
        emit_index = 0
        agent = self._agent_factory()

        def flush_visible() -> Iterator[str]:
            nonlocal emit_index, raw_buffer
            while True:
                # Handle orphaned </think> (no preceding <think>): skip everything before it
                orphan_end = raw_buffer.find("</think>", emit_index)
                think_start = raw_buffer.find("<think>", emit_index)
                if orphan_end != -1 and (think_start == -1 or orphan_end < think_start):
                    # Orphaned </think> — discard everything up to and including it
                    emit_index = orphan_end + len("</think>")
                    continue

                start = think_start
                if start == -1:
                    if emit_index < len(raw_buffer):
                        segment = raw_buffer[emit_index:]
                        emit_index = len(raw_buffer)
                        if segment:
                            yield segment
                    break

                if start > emit_index:
                    segment = raw_buffer[emit_index:start]
                    emit_index = start
                    if segment:
                        yield segment

                end = raw_buffer.find("</think>", start)
                if end == -1:
                    break
                emit_index = end + len("</think>")

        def generator() -> Iterator[str]:
            nonlocal raw_buffer, visible_output, emit_index
            try:
                for chunk in agent.stream_run(prompt):
                    raw_buffer += chunk
                    if remove_thinking:
                        for segment in flush_visible():
                            visible_output += segment
                            # Second safety net: strip any remaining think tags inline
                            clean = segment.replace("<think>", "").replace("</think>", "")
                            if clean.strip():
                                yield clean
                    else:
                        visible_output += chunk
                        if chunk:
                            yield chunk
            finally:
                if remove_thinking:
                    for segment in flush_visible():
                        visible_output += segment
                        clean = segment.replace("<think>", "").replace("</think>", "")
                        if clean.strip():
                            yield clean
                agent.clear_history()

        def get_summary() -> str:
            if remove_thinking:
                cleaned = strip_thinking_tokens(visible_output)
            else:
                cleaned = visible_output

            cleaned = strip_tool_calls(cleaned).strip()

            # 层1: 标题级去重 — LLM 多次输出 "## 任务总结"
            import re
            heading_pattern = re.compile(r"^(?:#{1,3}\s*)?任务总结", re.MULTILINE)
            matches = list(heading_pattern.finditer(cleaned))
            if len(matches) >= 2:
                cleaned = cleaned[matches[-1].start():].strip()

            # 层2: 发现级去重 — LLM 在同一个块内重复输出相同标题的发现
            # 按 ### N. 切分，对相同标题只保留最后一次
            finding_boundary = re.compile(r"^(?=###\s+\d+\.?\s)", re.MULTILINE)
            parts = finding_boundary.split(cleaned)
            if len(parts) > 1:
                # parts[0] 是第一个 ### 之前的内容（任务总结标题等）
                preamble = parts[0]
                seen: dict[str, int] = {}  # title_key -> index
                for i, section in enumerate(parts[1:], 1):
                    # Extract title from first line
                    first_line = section.split("\n", 1)[0].strip()
                    title_key = re.sub(r"^###\s*\d+\.?\s*", "", first_line).strip().lower()
                    seen[title_key] = i  # 后面的覆盖前面的 => 保留最后
                # Rebuild: preamble + unique sections (in original order, last occurrence)
                keep_indices = set(seen.values())
                rebuilt = [preamble]
                for i, section in enumerate(parts[1:], 1):
                    if i in keep_indices:
                        rebuilt.append(section)
                cleaned = "".join(rebuilt).strip()

            # Pydantic schema normalization
            cleaned = normalize_summary(cleaned)
            return cleaned

        return generator(), get_summary

    def _build_prompt(self, state: SummaryState, task: TodoItem, context: str,
                       skill_body: str = "") -> str:
        """Construct the summarization prompt shared by both modes."""

        prompt = (
            f"任务主题：{state.research_topic}\n"
            f"任务名称：{task.title}\n"
            f"任务目标：{task.intent}\n"
            f"检索查询：{task.query}\n"
            f"任务上下文：\n{context}\n"
            f"{build_note_guidance(task)}\n"
            "请生成一份面向用户的 Markdown 总结（遵循任务总结模板）。"
        )
        if skill_body:
            prompt += f"\n\n<SKILL_INSTRUCTIONS>\n{skill_body}\n</SKILL_INSTRUCTIONS>"
        return prompt
