"""Utility helpers for normalizing agent generated text."""

from __future__ import annotations

import re


def strip_tool_calls(text: str) -> str:
    """移除文本中的工具调用标记、裸 JSON 参数块、YAML frontmatter。"""

    if not text:
        return text

    # Remove [TOOL_CALL:note:{...}] markers
    text = re.compile(r"\[TOOL_CALL:[^\]]+\]").sub("", text)

    # Remove bare JSON arrays/objects that are leaked tool parameters
    text = re.compile(r"```(?:json)?\s*\n?\s*\[[\s\S]*?\"action\"[\s\S]*?\]\s*```", re.MULTILINE).sub("", text)
    text = re.compile(r'^\s*\{\s*"action"\s*:\s*"(?:create|update|read|delete)"[\s\S]*?\}\s*$', re.MULTILINE).sub("", text)

    # Strip YAML frontmatter (---\n...\n---) that may leak from note content
    text = re.sub(r"^---\s*\n(?:.*?\n)+?---\s*\n?", "", text, count=1, flags=re.MULTILINE)

    return text.strip()

