"""Context Builder (MASTER_INSTRUCTION.md Bab 29 step 7) — assemble prompt-ready context.

Formats ranked chunks into a citation-annotated block for injection into an
LLM prompt (Bab 29 rule 3 — sources must be traceable so RAG answers can cite
accurately), truncated to ``RAG_MAX_CONTEXT_CHARS`` so a large retrieval never
blows the prompt budget. This is a RAG-specific char budget for retrieved
chunks alone, distinct from the conversation-level Context Window Management
in Bab 50.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .knowledge_store import KnowledgeHit


@dataclass(frozen=True)
class BuiltContext:
    """The assembled context block plus which hits made it in (for citations)."""

    text: str
    included: list[KnowledgeHit] = field(default_factory=list)
    truncated: bool = False


def _citation_label(hit: KnowledgeHit, index: int) -> str:
    source = hit.metadata.get("source") or hit.metadata.get("filename") or hit.entry_id
    return f"[{index}] {source}"


def build_context(hits: list[KnowledgeHit], max_chars: int | None = None) -> BuiltContext:
    """Assemble ``hits`` into one citation-annotated context block under a char budget."""
    from api.config import settings

    max_chars = settings.RAG_MAX_CONTEXT_CHARS if max_chars is None else max_chars

    parts: list[str] = []
    included: list[KnowledgeHit] = []
    total = 0
    truncated = False

    for i, hit in enumerate(hits, start=1):
        block = f"{_citation_label(hit, i)}\n{hit.text}"
        block_len = len(block) + 2  # "\n\n" separator between blocks
        if total + block_len > max_chars:
            truncated = True
            break
        parts.append(block)
        included.append(hit)
        total += block_len

    return BuiltContext(text="\n\n".join(parts), included=included, truncated=truncated)
