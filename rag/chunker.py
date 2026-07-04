"""Chunker (MASTER_INSTRUCTION.md Bab 29 step 1) — split documents into indexable pieces.

Character-count chunking with overlap, snapping to the nearest whitespace so
chunks don't split mid-word. Documented strategy (Bab 29 rule 1): default
size/overlap come from ``RAG_CHUNK_SIZE``/``RAG_CHUNK_OVERLAP`` so ingestion
is reproducible across runs.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    """One chunk of a source document, with its position for citation/debugging."""

    text: str
    index: int
    start_char: int
    end_char: int


def chunk_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[Chunk]:
    """Split ``text`` into overlapping chunks of ~``chunk_size`` characters.

    Args:
        chunk_size: Target chunk width in characters; defaults to
            ``settings.RAG_CHUNK_SIZE``.
        overlap: Characters repeated between consecutive chunks, so a fact
            spanning a chunk boundary isn't lost to either side; defaults to
            ``settings.RAG_CHUNK_OVERLAP``.

    Raises:
        ValueError: If ``overlap >= chunk_size`` (chunking would never advance).
    """
    from api.config import settings

    chunk_size = settings.RAG_CHUNK_SIZE if chunk_size is None else chunk_size
    overlap = settings.RAG_CHUNK_OVERLAP if overlap is None else overlap
    if overlap >= chunk_size:
        raise ValueError(f"overlap ({overlap}) must be smaller than chunk_size ({chunk_size})")

    text = text.strip()
    if not text:
        return []

    chunks: list[Chunk] = []
    start = 0
    index = 0
    length = len(text)
    step = chunk_size - overlap

    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            boundary = text.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        piece = text[start:end].strip()
        if piece:
            chunks.append(Chunk(text=piece, index=index, start_char=start, end_char=end))
            index += 1
        start += step

    return chunks
