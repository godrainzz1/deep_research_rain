"""Service responsible for converting the research topic into actionable tasks."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, List, Optional

from hello_agents import ToolAwareSimpleAgent

from models import SummaryState, TodoItem
from config import Configuration
from prompts import get_current_date, todo_planner_instructions
from utils import strip_thinking_tokens

logger = logging.getLogger(__name__)

TOOL_CALL_PREFIX = "[TOOL_CALL:"
TOOL_CALL_PATTERN = re.compile(
    r"\[TOOL_CALL:(?P<tool>[^:]+):(?P<body>\{.*?\}\])(?=\[TOOL_CALL|$)",
    re.IGNORECASE | re.DOTALL,
)


def _extract_all_tool_call_bodies(text: str) -> list[str]:
    """Extract JSON bodies from all [TOOL_CALL:...] markers.

    Handles nested brackets inside JSON arrays by counting brace depth.
    """
    bodies: list[str] = []
    idx = 0
    prefix_lower = TOOL_CALL_PREFIX.lower()
    while True:
        start = text.lower().find(prefix_lower, idx)
        if start == -1:
            break
        # Find the colon separating tool name from body
        colon = text.find(":", start + len(prefix_lower))
        if colon == -1:
            idx = start + 1
            continue
        # Find the opening brace of the JSON body
        brace_start = text.find("{", colon + 1)
        if brace_start == -1:
            idx = start + 1
            continue
        # Count braces to find matching closing brace
        depth = 0
        brace_end = -1
        for i in range(brace_start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    brace_end = i
                    break
        if brace_end == -1:
            idx = start + 1
            continue
        body = text[brace_start : brace_end + 1]
        bodies.append(body)
        idx = brace_end + 1
    return bodies

class PlanningService:
    """Wraps the planner agent to produce structured TODO items."""

    def __init__(self, planner_agent: ToolAwareSimpleAgent, config: Configuration) -> None:
        self._agent = planner_agent
        self._config = config

    def plan_todo_list(self, state: SummaryState) -> List[TodoItem]:
        """Ask the planner agent to break the topic into actionable tasks."""

        prompt = todo_planner_instructions.format(
            current_date=get_current_date(),
            research_topic=state.research_topic,
        )

        response = self._agent.run(prompt)
        self._agent.clear_history()

        logger.info("Planner raw output (truncated): %s", response[:500])

        tasks_payload = self._extract_tasks(response)
        todo_items: List[TodoItem] = []

        for idx, item in enumerate(tasks_payload, start=1):
            title = str(item.get("title") or f"任务{idx}").strip()
            intent = str(item.get("intent") or "聚焦主题的关键问题").strip()
            query = str(item.get("query") or state.research_topic).strip()

            if not query:
                query = state.research_topic

            task = TodoItem(
                id=idx,
                title=title,
                intent=intent,
                query=query,
            )
            todo_items.append(task)

        state.todo_items = todo_items

        titles = [task.title for task in todo_items]
        logger.info("Planner produced %d tasks: %s", len(todo_items), titles)
        return todo_items

    @staticmethod
    def create_fallback_task(state: SummaryState) -> TodoItem:
        """Create a minimal fallback task when planning failed."""

        return TodoItem(
            id=1,
            title="基础背景梳理",
            intent="收集主题的核心背景与最新动态",
            query=f"{state.research_topic} 最新进展" if state.research_topic else "基础背景梳理",
        )

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------
    def _extract_tasks(self, raw_response: str) -> List[dict[str, Any]]:
        """Parse planner output into a list of task dictionaries.

        Handles both structured JSON responses and [TOOL_CALL:note:...] format
        when the planner was instructed to use the note tool.
        """
        text = raw_response.strip()
        if self._config.strip_thinking_tokens:
            text = strip_thinking_tokens(text)

        json_payload = self._extract_json_payload(text)
        tasks: List[dict[str, Any]] = []

        if isinstance(json_payload, dict):
            candidate = json_payload.get("tasks")
            if isinstance(candidate, list):
                for item in candidate:
                    if isinstance(item, dict):
                        tasks.append(item)
        elif isinstance(json_payload, list):
            for item in json_payload:
                if isinstance(item, dict):
                    tasks.append(item)

        # Fallback 1: single tool call with embedded tasks list
        if not tasks:
            tool_payload = self._extract_tool_payload(text)
            if tool_payload and isinstance(tool_payload.get("tasks"), list):
                for item in tool_payload["tasks"]:
                    if isinstance(item, dict):
                        tasks.append(item)

        # Fallback 2: multiple [TOOL_CALL:note:...] entries — extract task
        # parameters from each note creation call
        if not tasks:
            tasks = self._extract_tasks_from_note_calls(text)

        return tasks

    def _extract_tasks_from_note_calls(self, text: str) -> List[dict[str, Any]]:
        """Extract tasks from individual [TOOL_CALL:note:{...}] entries."""
        tasks: List[dict[str, Any]] = []
        for body in _extract_all_tool_call_bodies(text):
            try:
                params = json.loads(body)
            except json.JSONDecodeError:
                continue
            if not isinstance(params, dict):
                continue
            # Only process "create" actions (task initialization)
            if params.get("action") != "create":
                continue

            task_id = params.get("task_id")
            title = params.get("title", "")
            content = params.get("content", "")

            # Strip "任务 N: " prefix from title
            if isinstance(title, str) and title.startswith("任务"):
                colon_idx = title.find(": ")
                if colon_idx != -1:
                    title = title[colon_idx + 2:]

            # Infer intent & query from content field
            intent = ""
            query = ""
            if isinstance(content, str):
                for line in content.replace("：", ":").split("\n"):
                    line = line.strip()
                    if any(line.startswith(p) for p in ("任务概览:", "目标:", "意图:", "intent:")):
                        intent = line.split(":", 1)[-1].strip()
                    elif any(line.startswith(p) for p in ("检索方向:", "查询:", "搜索:", "query:")):
                        query = line.split(":", 1)[-1].strip()

            tasks.append({
                "title": str(title).strip() if title else f"任务{task_id}",
                "intent": intent or str(title).strip(),
                "query": query or str(title).strip(),
            })

        return tasks

    def _extract_json_payload(self, text: str) -> Optional[dict[str, Any] | list]:
        """Try to locate and parse a JSON object or array from the text."""

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                return None

        return None

    def _extract_tool_payload(self, text: str) -> Optional[dict[str, Any]]:
        """Parse the first TOOL_CALL expression in the output."""

        match = TOOL_CALL_PATTERN.search(text)
        if not match:
            return None

        body = match.group("body")

        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

        parts = [segment.strip() for segment in body.split(",") if segment.strip()]
        payload: dict[str, Any] = {}
        for part in parts:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            payload[key.strip()] = value.strip().strip('"').strip("'")

        return payload or None
