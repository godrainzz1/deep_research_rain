"""Helpers for coordinating note tool usage instructions."""

from __future__ import annotations

import json

from models import TodoItem


def build_note_guidance(task: TodoItem) -> str:
    """Generate note tool usage guidance for a specific task.

    程序化 create/update 已由 _ensure_task_note / _update_task_note 保证执行。
    此处只引导 LLM 读取笔记获取上下文，不再劝其自行 create/update ——
    LLM 的工具调用会触发重新生成，导致前端重复输出。
    """

    tags_list = ["deep_research", f"task_{task.id}"]
    tags_literal = json.dumps(tags_list, ensure_ascii=False)

    if task.note_id:
        read_payload = json.dumps(
            {"action": "read", "note_id": task.note_id}, ensure_ascii=False
        )

        return (
            "笔记协作指引：\n"
            f"- 当前任务笔记 ID：{task.note_id}（笔记已由系统自动创建，无需你再创建或更新）。\n"
            f"- 在书写总结前建议先读取笔记了解任务背景：\n"
            f"  [TOOL_CALL:note:{read_payload}]\n"
            "- 读取笔记后直接输出面向用户的 Markdown 总结，不要再调用 update。\n"
            "- 系统会在你输出完成后自动将总结写入笔记。\n"
        )

    # 不应到达这里（_ensure_task_note 已保证 note_id 存在），
    # 保留兜底以防极少数竞态
    return (
        "笔记协作指引：\n"
        "- 任务笔记将由系统自动创建，请直接输出面向用户的 Markdown 总结。\n"
    )
