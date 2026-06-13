"""Text chunking strategies for RAG ingestion."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)
    chunk_index: int = 0


def recursive_chunk(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    separators: list[str] | None = None,
) -> list[Chunk]:
    """Split text recursively using a priority-ordered list of separators.

    Default separators are tuned for Chinese + English mixed content.
    """
    if separators is None:
        separators = ["\n\n", "\n", "。", ". ", "？", "！", "；", ";", "，", ", ", " ", ""]

    # Estimate characters: ~2 chars per token for mixed Chinese/English
    char_limit = chunk_size * 2
    char_overlap = chunk_overlap * 2

    chunks: list[str] = _split_recursive(text.strip(), separators, char_limit, char_overlap)

    return [
        Chunk(text=chunk.strip(), chunk_index=i)
        for i, chunk in enumerate(chunks)
        if chunk.strip()
    ]


def _split_recursive(
    text: str,
    separators: list[str],
    limit: int,
    overlap: int,
) -> list[str]:
    """Internal: recursively split text by the most effective separator."""
    if not text.strip():
        return []

    # Try each separator in order
    best_sep = ""
    best_splits: list[str] = []
    for sep in separators:
        splits = text.split(sep) if sep else [text]
        if len(splits) > 1:
            best_sep = sep
            best_splits = splits
            break

    if not best_splits:
        return [text]

    # Merge splits that are too short, split those that are too long
    result: list[str] = []
    buffer = ""
    for part in best_splits:
        candidate = buffer + (best_sep if buffer else "") + part
        if len(candidate) <= limit:
            buffer = candidate
        else:
            if buffer:
                result.append(buffer)
            # If a single split is still too long, recurse on remaining separators
            if len(part) > limit:
                remaining_seps = separators[separators.index(best_sep) + 1:]
                sub_chunks = _split_recursive(part, remaining_seps, limit, overlap)
                result.extend(sub_chunks)
                buffer = ""
            else:
                buffer = part

    if buffer:
        result.append(buffer)

    # Apply overlap: add trailing context from previous chunk
    if overlap > 0 and len(result) > 1:
        overlapped = [result[0]]
        for i in range(1, len(result)):
            prev = result[i - 1]
            if len(prev) > overlap:
                prev_tail = prev[-overlap:]
            else:
                prev_tail = prev
            overlapped.append(prev_tail + result[i])
        return overlapped

    return result


def semantic_chunk(
    text: str,
    min_chunk_size: int = 128,
    max_chunk_size: int = 1024,
) -> list[Chunk]:
    """Paragraph-based chunking — splits on double-newlines.

    Short paragraphs are merged until *min_chunk_size* is reached;
    long paragraphs are split when exceeding *max_chunk_size*.
    Both sizes are measured in characters (~2 chars/token for mixed CN/EN).
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    buffer = ""
    for p in paragraphs:
        combined = f"{buffer}\n\n{p}" if buffer else p
        if len(combined) <= max_chunk_size * 2:
            buffer = combined
        else:
            if buffer and len(buffer) >= min_chunk_size * 2:
                chunks.append(buffer)
                buffer = p
            else:
                buffer = combined  # keep merging until big enough

    if buffer:
        chunks.append(buffer)

    return [
        Chunk(text=c.strip(), chunk_index=i)
        for i, c in enumerate(chunks)
        if c.strip()
    ]
