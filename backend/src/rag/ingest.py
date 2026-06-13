"""One-click ingestion pipeline: parse → chunk → embed → store."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

from rag.parser import parse_file, ParsedDocument
from rag.chunker import recursive_chunk, Chunk
from rag.embedder import get_embedder, OllamaEmbedder
from rag.store import get_vector_store, VectorStore

logger = logging.getLogger(__name__)


def ingest_file(
    file_path: str | Path,
    collection: str = "knowledge_base",
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> int:
    """Parse → chunk → embed → store a single file.

    Returns the number of chunks ingested.
    """
    # 1. Parse
    doc: Optional[ParsedDocument] = parse_file(file_path)
    if doc is None:
        logger.error("Failed to parse %s — skipping ingestion", file_path)
        return 0

    # 2. Chunk
    chunks: list[Chunk] = recursive_chunk(doc.content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not chunks:
        logger.warning("No chunks produced for %s", file_path)
        return 0

    # Attach metadata to each chunk
    for c in chunks:
        c.metadata = {
            "source_file": doc.file_path,
            "source_title": doc.title,
            "format": doc.metadata.get("format", ""),
            "chunk_index": c.chunk_index,
        }

    # 3. Embed
    embedder: OllamaEmbedder = get_embedder()
    texts = [c.text for c in chunks]
    try:
        embeddings = embedder.embed_batch(texts)
    except Exception:
        logger.exception("Embedding failed for %s", file_path)
        return 0

    # 4. Store
    store: VectorStore = get_vector_store()
    ids = [f"{doc.title}_{c.chunk_index}_{uuid.uuid4().hex[:8]}" for c in chunks]
    metadatas = [c.metadata for c in chunks]

    store.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas, collection=collection)

    logger.info("Ingested %s → %d chunks into %s", doc.title, len(chunks), collection)
    return len(chunks)


def ingest_directory(
    dir_path: str | Path,
    collection: str = "knowledge_base",
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> dict[str, int]:
    """Ingest all supported files in a directory. Returns {filename: chunks}."""
    path = Path(dir_path)
    if not path.is_dir():
        logger.error("Not a directory: %s", path)
        return {}

    results: dict[str, int] = {}
    for f in sorted(path.iterdir()):
        if f.is_file() and f.suffix.lower() in {".pdf", ".docx", ".doc", ".md", ".txt"}:
            count = ingest_file(f, collection=collection, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            if count > 0:
                results[f.name] = count

    logger.info("Ingested %d files → %d total chunks", len(results), sum(results.values()))
    return results
