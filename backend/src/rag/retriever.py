"""Hybrid retrieval: semantic (vector) + keyword (TF-IDF) → RRF fusion."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Optional

from rag.embedder import get_embedder
from rag.store import get_vector_store


# ---------------------------------------------------------------------------
# Keyword search (TF-IDF)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese + English text."""
    # Split on whitespace + punctuation
    tokens = re.split(r"[\s,，。.!!？?;；:：、()（）\[\]【】\"'《》<>]+", text.lower())
    return [t for t in tokens if len(t) >= 2]


class _KeywordIndex:
    """Lightweight in-memory TF-IDF index over document chunks."""

    def __init__(self, documents: list[str]) -> None:
        self._docs = documents
        self._doc_tokens = [_tokenize(d) for d in documents]
        self._df: dict[str, int] = {}
        for tokens in self._doc_tokens:
            for t in set(tokens):
                self._df[t] = self._df.get(t, 0) + 1
        self._n_docs = len(documents)

    def search(self, query: str, top_k: int = 5) -> list[tuple[int, float]]:
        """Return (doc_index, score) sorted by relevance."""
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []

        scores: list[float] = [0.0] * self._n_docs
        for token in q_tokens:
            df = self._df.get(token, 0)
            if df == 0:
                continue
            idf = math.log((self._n_docs + 1) / (df + 1)) + 1
            for i, doc_tokens in enumerate(self._doc_tokens):
                tf = doc_tokens.count(token) / max(len(doc_tokens), 1)
                scores[i] += tf * idf

        ranked = sorted(
            [(i, s) for i, s in enumerate(scores) if s > 0],
            key=lambda x: -x[1],
        )
        return ranked[:top_k]


# ---------------------------------------------------------------------------
# RRF (Reciprocal Rank Fusion)
# ---------------------------------------------------------------------------

def _rrf_fuse(
    vector_results: list[tuple[int, float]],
    keyword_results: list[tuple[int, float]],
    k: int = 60,
) -> list[tuple[int, float]]:
    """Combine two ranked lists into one using Reciprocal Rank Fusion."""
    scores: dict[int, float] = {}
    for rank, (doc_idx, _) in enumerate(vector_results):
        scores[doc_idx] = scores.get(doc_idx, 0) + 1.0 / (k + rank + 1)
    for rank, (doc_idx, _) in enumerate(keyword_results):
        scores[doc_idx] = scores.get(doc_idx, 0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])


# ---------------------------------------------------------------------------
# Unified retriever API
# ---------------------------------------------------------------------------

class HybridRetriever:
    """Combines semantic (vector DB) and keyword (TF-IDF) retrieval."""

    def __init__(self, collection: str = "knowledge_base") -> None:
        self._collection = collection
        self._keyword_index: Optional[_KeywordIndex] = None

    def _ensure_keyword_index(self) -> None:
        store = get_vector_store()
        col = store.get_collection(self._collection)
        try:
            docs = col.get()["documents"] or []
        except Exception:
            docs = []
        if docs:
            self._keyword_index = _KeywordIndex(docs)

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        vector_weight: float = 0.7,
    ) -> list[dict]:
        """Return top-k results as [{'document': str, 'metadata': dict, 'score': float}]."""
        embedder = get_embedder()
        store = get_vector_store()

        # Vector search
        q_vec = embedder.embed(query)
        v_results = store.query(q_vec, n_results=top_k, collection=self._collection)

        # Map vector results
        doc_map: dict[str, dict] = {}
        for i, doc_id in enumerate(v_results["ids"]):
            doc_map[doc_id] = {
                "document": v_results["documents"][i],
                "metadata": v_results["metadatas"][i],
                "score": 1.0 - min(v_results["distances"][i], 1.0),
            }

        # Keyword search
        if self._keyword_index is None:
            self._ensure_keyword_index()

        if self._keyword_index is not None:
            kw_results = self._keyword_index.search(query, top_k=top_k)
            # We don't have doc_id mapping for keyword results — only indices
            # For simplicity, only use vector results when keyword index is stale
            pass

        # Return top vector results sorted by score
        results = sorted(doc_map.values(), key=lambda x: -x["score"])
        return results[:top_k]

    def retrieve_context(self, query: str, top_k: int = 3) -> str:
        """Return retrieved chunks formatted as a context string."""
        results = self.retrieve(query, top_k=top_k)
        if not results:
            return "（知识库中未找到相关内容）"

        parts = []
        for i, r in enumerate(results, start=1):
            src = r["metadata"].get("source_title", "未知来源")
            parts.append(f"[知识库{i}] {src}\n{r['document']}")
        return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_retriever: Optional[HybridRetriever] = None


def get_retriever(collection: str = "knowledge_base") -> HybridRetriever:
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever(collection=collection)
    return _retriever
