"""Search dispatch helpers leveraging HelloAgents SearchTool."""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

from hello_agents.tools import SearchTool

from config import Configuration
from utils import (
    deduplicate_and_format_sources,
    format_sources,
    get_config_value,
)
from services.search_quality import (
    deduplicate_results,
    generate_sub_queries,
    score_and_filter_results,
    should_rewrite,
)

logger = logging.getLogger(__name__)

MAX_TOKENS_PER_SOURCE = 2000


def _create_search_tool(search_api: str) -> SearchTool:
    """Create a SearchTool instance for the requested backend.

    Uses the configured backend as the default, falling back to DuckDuckGo
    when the requested backend is unavailable or unspecified.
    """
    return SearchTool(backend=search_api)


def dispatch_search(
    query: str,
    config: Configuration,
    loop_count: int,
) -> Tuple[dict[str, Any] | None, list[str], Optional[str], str]:
    """Execute configured search backend and normalise response payload."""

    search_api = get_config_value(config.search_api)
    search_tool = _create_search_tool(search_api)

    try:
        raw_response = search_tool.run(
            {
                "input": query,
                "backend": search_api,
                "mode": "structured",
                "fetch_full_page": config.fetch_full_page,
                "max_results": 5,
                "max_tokens_per_source": MAX_TOKENS_PER_SOURCE,
                "loop_count": loop_count,
            }
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Search backend %s failed: %s", search_api, exc)
        raise

    if isinstance(raw_response, str):
        notices = [raw_response]
        logger.warning("Search backend %s returned text notice: %s", search_api, raw_response)
        payload: dict[str, Any] = {
            "results": [],
            "backend": search_api,
            "answer": None,
            "notices": notices,
        }
    else:
        payload = raw_response
        notices = list(payload.get("notices") or [])

    backend_label = str(payload.get("backend") or search_api)
    answer_text = payload.get("answer")
    results = payload.get("results", [])

    # --- Quality pipeline ---
    if results:
        before = len(results)
        results = score_and_filter_results(results)
        results = deduplicate_results(results, threshold=0.75)
        payload["results"] = results
        logger.info("Search quality: %d → %d results (filtered + deduped)", before, len(results))

    # --- Sub-query hint ---
    if should_rewrite(query):
        subs = generate_sub_queries(query, max_sub=3)
        logger.info("Broad query detected — sub-queries: %s", subs)
        payload.setdefault("sub_queries", subs)

    if notices:
        for notice in notices:
            logger.info("Search notice (%s): %s", backend_label, notice)

    logger.info(
        "Search backend=%s resolved_backend=%s answer=%s results=%s",
        search_api,
        backend_label,
        bool(answer_text),
        len(results),
    )

    return payload, notices, answer_text, backend_label


def prepare_research_context(
    search_result: dict[str, Any] | None,
    answer_text: Optional[str],
    config: Configuration,
    *,
    rag_query: str = "",
) -> tuple[str, str]:
    """Build structured context and source summary for downstream agents.

    When the RAG knowledge base is available, local chunks are merged
    alongside web search results.
    """
    # --- Web results ---
    sources_summary = format_sources(search_result)
    context = deduplicate_and_format_sources(
        search_result or {"results": []},
        max_tokens_per_source=MAX_TOKENS_PER_SOURCE,
        fetch_full_page=config.fetch_full_page,
    )

    if answer_text:
        context = f"AI直接答案：\n{answer_text}\n\n{context}"

    # --- RAG knowledge base (only when documents have been uploaded) ---
    if rag_query:
        try:
            from rag.retriever import get_retriever
            from rag.store import get_vector_store
            store = get_vector_store()
            kb_count = store.count("knowledge_base")
            if kb_count > 0:
                retriever = get_retriever()
                kb_context = retriever.retrieve_context(query=rag_query, top_k=3)
                if kb_context and "未找到" not in kb_context:
                    context = f"{context}\n\n--- 📚 本地知识库（共{kb_count}个文本块，以下为最相关片段） ---\n{kb_context}"
                    logger.info("RAG: merged %d local chunks (kb total=%d)", 3, kb_count)
            else:
                logger.debug("RAG skipped — knowledge base is empty, upload files first")
        except Exception:
            logger.debug("RAG not available — using web-only context")

    return sources_summary, context
