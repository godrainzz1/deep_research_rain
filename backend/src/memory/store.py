"""Persistent memory — SQLite for sessions/preferences + ChromaDB for semantic recall."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB = "./memory.db"


# ---------------------------------------------------------------------------
# SQLite backend
# ---------------------------------------------------------------------------

class MemoryStore:
    """SQLite-backed store for research history, preferences, and FAQs."""

    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        self._db = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._create_tables()
        return self._conn

    def _create_tables(self) -> None:
        conn = self._conn
        if conn is None:
            return
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                report_markdown TEXT,
                created_at REAL NOT NULL,
                metadata TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS faqs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                count INTEGER DEFAULT 1,
                created_at REAL NOT NULL
            );
        """)
        conn.commit()

    # -- sessions ---------------------------------------------------------

    def save_session(self, session_id: str, topic: str, report: str, metadata: dict | None = None) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO sessions (id, topic, report_markdown, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
            (session_id, topic, report, time.time(), json.dumps(metadata or {}, ensure_ascii=False)),
        )
        conn.commit()

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, topic, created_at FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [{"id": r["id"], "topic": r["topic"], "created_at": r["created_at"]} for r in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return dict(row)

    def delete_session(self, session_id: str) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()

    # -- preferences ------------------------------------------------------

    def set_preference(self, key: str, value: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO preferences (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, time.time()),
        )
        conn.commit()

    def get_preference(self, key: str) -> str | None:
        conn = self._get_conn()
        row = conn.execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def list_preferences(self) -> dict[str, str]:
        conn = self._get_conn()
        rows = conn.execute("SELECT key, value FROM preferences").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # -- FAQs -------------------------------------------------------------

    def upsert_faq(self, question: str, answer: str) -> None:
        conn = self._get_conn()
        existing = conn.execute("SELECT id, count FROM faqs WHERE question = ?", (question,)).fetchone()
        if existing:
            conn.execute("UPDATE faqs SET count = count + 1, answer = ? WHERE id = ?", (answer, existing["id"]))
        else:
            conn.execute(
                "INSERT INTO faqs (question, answer, created_at) VALUES (?, ?, ?)",
                (question, answer, time.time()),
            )
        conn.commit()

    def list_faqs(self, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute("SELECT question, answer, count FROM faqs ORDER BY count DESC LIMIT ?", (limit,)).fetchall()
        return [{"question": r["question"], "answer": r["answer"], "count": r["count"]} for r in rows]


# ---------------------------------------------------------------------------
# Semantic memory (ChromaDB-based)
# ---------------------------------------------------------------------------

class SemanticMemory:
    """Store and recall knowledge cards using ChromaDB."""

    COLLECTION = "semantic_memory"

    def __init__(self) -> None:
        self._store = None

    def _ensure_store(self):
        if self._store is not None:
            return
        from rag.store import get_vector_store
        self._store = get_vector_store()
        try:
            self._store.get_collection(self.COLLECTION)
        except Exception:
            self._store.reset(self.COLLECTION)

    def store_knowledge_card(self, topic: str, summary: str, metadata: dict | None = None) -> None:
        """Embed and store a research summary as a knowledge card."""
        self._ensure_store()
        from rag.embedder import get_embedder
        emb = get_embedder()
        vec = emb.embed(f"{topic}: {summary}")
        import uuid
        card_id = f"card_{topic}_{uuid.uuid4().hex[:8]}"
        self._store.add(
            ids=[card_id],
            documents=[f"{topic}: {summary}"],
            embeddings=[vec],
            metadatas=[metadata or {"topic": topic}],
            collection=self.COLLECTION,
        )

    def recall(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Semantically search past knowledge cards."""
        self._ensure_store()
        from rag.embedder import get_embedder
        emb = get_embedder()
        q_vec = emb.embed(query)
        results = self._store.query(q_vec, n_results=top_k, collection=self.COLLECTION)
        cards = []
        for i, doc_id in enumerate(results["ids"]):
            cards.append({
                "id": doc_id,
                "document": results["documents"][i],
                "metadata": results["metadatas"][i],
                "distance": results["distances"][i],
            })
        return cards


# ---------------------------------------------------------------------------
# Topic detection
# ---------------------------------------------------------------------------

def check_similar_topic(topic: str, threshold: float = 0.8) -> list[dict[str, Any]]:
    """Return past sessions with similar topics (semantic similarity check)."""
    try:
        sem = SemanticMemory()
        cards = sem.recall(topic, top_k=3)
        # ChromaDB returns cosine distance; convert to similarity
        similar = [c for c in cards if 1.0 - c["distance"] >= threshold]
        return similar
    except Exception:
        logger.debug("Semantic memory unavailable — skipping topic detection")
        return []


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_memory_store: Optional[MemoryStore] = None


def get_memory_store(db_path: str = _DEFAULT_DB) -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore(db_path=db_path)
    return _memory_store
