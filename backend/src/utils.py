"""Utility helpers shared across deep researcher services."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Union

CHARS_PER_TOKEN = 4

logger = logging.getLogger(__name__)


def get_config_value(value: Any) -> str:
    """Return configuration value as plain string."""

    return value if isinstance(value, str) else value.value


def strip_thinking_tokens(text: str) -> str:
    """Remove ``<think>`` sections from model responses."""

    while "<think>" in text and "</think>" in text:
        start = text.find("<think>")
        end = text.find("</think>") + len("</think>")
        text = text[:start] + text[end:]
    return text


def deduplicate_and_format_sources(
    search_response: Dict[str, Any] | List[Dict[str, Any]],
    max_tokens_per_source: int,
    *,
    fetch_full_page: bool = False,
) -> str:
    """Format and deduplicate search results for downstream prompting."""

    if isinstance(search_response, dict):
        sources_list = search_response.get("results", [])
    else:
        sources_list = search_response

    unique_sources: dict[str, Dict[str, Any]] = {}
    for source in sources_list:
        url = source.get("url")
        if not url:
            continue
        if url not in unique_sources:
            unique_sources[url] = source

    formatted_parts: List[str] = []
    # 编号来源列表（供 LLM 引用）
    ref_lines: List[str] = []
    for idx, source in enumerate(unique_sources.values(), start=1):
        title = source.get("title") or source.get("url", "")
        content = source.get("content", "")
        formatted_parts.append(f"[来源{idx}] 标题: {title}\n\n")
        formatted_parts.append(f"[来源{idx}] URL: {source.get('url', '')}\n\n")
        formatted_parts.append(f"[来源{idx}] 内容: {content}\n\n")
        ref_lines.append(f"[{idx}] {title} — {source.get('url', '')}")

        if fetch_full_page:
            raw_content = source.get("raw_content")
            if raw_content is None:
                logger.debug("raw_content missing for %s", source.get("url", ""))
                raw_content = ""
            char_limit = max_tokens_per_source * CHARS_PER_TOKEN
            if len(raw_content) > char_limit:
                raw_content = f"{raw_content[:char_limit]}... [truncated]"
            formatted_parts.append(
                f"详细信息内容限制为 {max_tokens_per_source} 个 token: {raw_content}\n\n"
            )

    # 附加引用速查表
    if ref_lines:
        formatted_parts.append("\n--- 引用速查 ---\n")
        formatted_parts.append("\n".join(ref_lines))
        formatted_parts.append("\n请在总结中使用 [1]、[2] 等编号引用以上来源。\n")

    return "".join(formatted_parts).strip()


def format_sources(search_results: Dict[str, Any] | None) -> str:
    """Return numbered reference list matching the context's citation IDs."""

    if not search_results:
        return ""

    results = search_results.get("results", [])
    parts = []
    for idx, item in enumerate(results, start=1):
        url = item.get("url", "")
        if not url:
            continue
        title = item.get("title") or url
        parts.append(f"[{idx}] {title} — {url}")
    return "\n".join(parts) if parts else ""
