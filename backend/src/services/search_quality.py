"""Search quality enhancements — query rewriting, source scoring, dedup."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Query rewriting
# ---------------------------------------------------------------------------

# Broad/generic queries that benefit from being split into sub-queries
_BROAD_PATTERNS = [
    (r"^(什么是|What is|Who is|介绍一下|概述|综述|总结)", True),
    (r"^(最新|近期|202[0-9]|趋势|发展|前景|未来)", True),
    (r"^[\w一-鿿]{1,3}$", True),  # Very short queries
]

# Domain-specific sub-query templates
_SUB_QUERY_TEMPLATES = [
    "{query} 定义 概念",
    "{query} 最新进展 2025 2026",
    "{query} 关键问题 挑战",
    "{query} 应用案例 实践",
]


def should_rewrite(query: str) -> bool:
    """Heuristic: does this query look like it would benefit from being split?"""
    query = query.strip()
    if len(query) <= 5 and not any(kw in query for kw in ["怎么", "如何", "为什么", "how", "why"]):
        return True
    return False


def generate_sub_queries(query: str, max_sub: int = 3) -> list[str]:
    """Generate sub-queries for broad topics (rule-based, no LLM call)."""
    if not should_rewrite(query):
        return [query]

    subs = []
    for tmpl in _SUB_QUERY_TEMPLATES:
        if len(subs) >= max_sub:
            break
        sub = tmpl.format(query=query)
        if sub != query:
            subs.append(sub)
    return subs if subs else [query]


# ---------------------------------------------------------------------------
# Source credibility scoring
# ---------------------------------------------------------------------------

# Domain credibility tiers — higher = more authoritative
_CREDIBILITY_RULES: list[tuple[str, int]] = [
    # Tier 5: Government & education
    (r"\.gov\b", 5),
    (r"\.edu\b", 5),
    (r"\.ac\b", 5),
    # Tier 4: Academic repositories
    (r"arxiv\.org", 4),
    (r"semanticscholar\.org", 4),
    (r"scholar\.google\.", 4),
    (r"doi\.org", 4),
    # Tier 3: Major publications & encyclopedias
    (r"wikipedia\.org", 3),
    (r"baidu\.com/item", 3),  # Baidu Baike
    (r"reuters\.com", 3),
    (r"bbc\.", 3),
    (r"nature\.com", 3),
    (r"science\.org", 3),
    # Tier 2: General news & tech media
    (r"github\.com", 2),
    (r"medium\.com", 2),
    (r"zhihu\.com", 2),
    (r"36kr\.com", 2),
    # Tier 1: Default — everything else
    (r".*", 1),
]


def score_source(url: str) -> int:
    """Return a credibility score (1-5) for a source URL."""
    if not url:
        return 0
    try:
        domain = urlparse(url).netloc or url
    except Exception:
        domain = url
    for pattern, score in _CREDIBILITY_RULES:
        if re.search(pattern, domain, re.IGNORECASE):
            return score
    return 0


def is_low_quality(url: str, content: str = "") -> bool:
    """Quick filter for obviously low-quality sources."""
    if not url:
        return True

    domain = urlparse(url).netloc.lower()

    _low_quality_domains = {
        "example.com",
        "localhost",
        "127.0.0.1",
    }
    if domain in _low_quality_domains:
        return True

    return False


# ---------------------------------------------------------------------------
# Semantic deduplication (lightweight — token overlap based)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Simple tokenisation for Chinese + English text."""
    # Split on whitespace + common punctuation
    tokens = re.split(r"[\s,，。.!！?？;；:：、()（）\[\]【】\"'《》<>]+", text.lower())
    return {t for t in tokens if len(t) >= 2}


def compute_overlap(a: str, b: str) -> float:
    """Jaccard similarity between two text strings."""
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta or not tb:
        return 0.0
    intersection = len(ta & tb)
    union = len(ta | tb)
    return intersection / union if union > 0 else 0.0


def deduplicate_results(results: list[dict[str, Any]], threshold: float = 0.75) -> list[dict[str, Any]]:
    """Remove near-duplicate search results by token overlap.

    Keeps the first result when similarity exceeds *threshold*.
    """
    if len(results) <= 1:
        return results

    kept: list[dict[str, Any]] = [results[0]]
    for candidate in results[1:]:
        ct = f"{candidate.get('title', '')} {candidate.get('content', '')[:200]}"
        is_dup = False
        for existing in kept:
            et = f"{existing.get('title', '')} {existing.get('content', '')[:200]}"
            if compute_overlap(ct, et) >= threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(candidate)

    return kept


def score_and_filter_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Annotate results with credibility scores and remove low-quality ones."""
    filtered = []
    for r in results:
        url = r.get("url", "")
        if is_low_quality(url, r.get("content", "")):
            continue
        r["credibility_score"] = score_source(url)
        filtered.append(r)
    # Sort by score descending
    filtered.sort(key=lambda x: x.get("credibility_score", 0), reverse=True)
    return filtered
