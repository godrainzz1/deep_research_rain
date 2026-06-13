"""ChromaDB vector store wrapper for RAG."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_COLLECTION = "knowledge_base"


class VectorStore:
    """Thin wrapper around ChromaDB for document chunk storage and retrieval."""

    def __init__(self, persist_dir: str = "./chroma_db") -> None:
        self._dir = Path(persist_dir)
        self._client: Any = None
        self._collection: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            import chromadb
        except ImportError:
            raise ImportError("chromadb is required. pip install chromadb")

        self._dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self._dir))

    def get_collection(self, name: str = _DEFAULT_COLLECTION) -> Any:
        """Return (or create) a named collection."""
        self._ensure_client()
        try:
            self._collection = self._client.get_collection(name)
        except Exception:
            self._collection = self._client.create_collection(name)
        return self._collection

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict] | None = None,
        collection: str = _DEFAULT_COLLECTION,
    ) -> None:
        col = self.get_collection(collection)
        col.add(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas or [{}] * len(ids))
        logger.info("Added %d chunks to collection %s", len(ids), collection)

    def query(
        self,
        query_embedding: list[float],
        n_results: int = 5,
        collection: str = _DEFAULT_COLLECTION,
    ) -> dict[str, Any]:
        col = self.get_collection(collection)
        results = col.query(query_embeddings=[query_embedding], n_results=n_results)
        return {
            "ids": results["ids"][0] if results["ids"] else [],
            "documents": results["documents"][0] if results["documents"] else [],
            "metadatas": results["metadatas"][0] if results["metadatas"] else [],
            "distances": results["distances"][0] if results["distances"] else [],
        }

    def delete(self, ids: list[str], collection: str = _DEFAULT_COLLECTION) -> None:
        col = self.get_collection(collection)
        col.delete(ids=ids)
        logger.info("Deleted %d chunks from collection %s", len(ids), collection)

    def count(self, collection: str = _DEFAULT_COLLECTION) -> int:
        col = self.get_collection(collection)
        return col.count()

    def list_collections(self) -> list[str]:
        self._ensure_client()
        return [c.name for c in self._client.list_collections()]

    def reset(self, collection: str = _DEFAULT_COLLECTION) -> None:
        """Drop and recreate a collection."""
        self._ensure_client()
        try:
            self._client.delete_collection(collection)
        except Exception:
            pass
        self._client.create_collection(collection)
        logger.info("Collection %s reset", collection)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_store: Optional[VectorStore] = None


def get_vector_store(persist_dir: str = "./chroma_db") -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore(persist_dir=persist_dir)
    return _store
