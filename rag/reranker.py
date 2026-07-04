"""Reranker (MASTER_INSTRUCTION.md Bab 29 step 6) — reorder candidates by relevance.

Default (:func:`rerank`): boosts hits containing exact code-like tokens from
the query — cheap, dependency-free, and directly addresses Bab 29 rule 2's
concern (certificate numbers, article numbers, IUP codes should outrank a
merely topically-similar chunk). Enabled via ``RAG_RERANK_ENABLED``.

:func:`llm_rerank` is a heavier, more accurate alternative that asks an LLM
(role ``critic``) to score the shortlist directly. It is **not** wired into
the default pipeline automatically — adding an LLM call to every retrieval
trades latency/cost that not every caller wants (Bab 27 spirit, even though
Cost Tracking itself is Tahap 6) — callers opt in explicitly.
"""
from __future__ import annotations

import json
import re

from core.utils.logger import get_logger

from .knowledge_store import KnowledgeHit

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Alphanumeric tokens with a digit and some length — code/identifier-shaped,
# not a common word (Bab 29 rule 2's "istilah teknis/hukum spesifik").
_CODE_RE = re.compile(r"^(?=[a-z0-9./-]{4,}$)(?=.*\d).+$")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def rerank(query: str, hits: list[KnowledgeHit], boost: float = 0.15, max_boost: float = 0.3) -> list[KnowledgeHit]:
    """Boost hits containing exact code-like tokens from ``query`` (Bab 29 rule 2)."""
    query_codes = {tok for tok in _tokenize(query) if _CODE_RE.match(tok)}
    if not query_codes:
        return hits

    reranked = []
    for hit in hits:
        doc_tokens = set(_tokenize(hit.text))
        matches = len(query_codes & doc_tokens)
        bump = min(matches * boost, max_boost)
        reranked.append(
            KnowledgeHit(
                entry_id=hit.entry_id, text=hit.text, score=min(hit.score + bump, 1.0), metadata=hit.metadata
            )
        )
    reranked.sort(key=lambda h: h.score, reverse=True)
    return reranked


async def llm_rerank(
    query: str, hits: list[KnowledgeHit], role: str = "critic", top_k: int | None = None
) -> list[KnowledgeHit]:
    """Ask an LLM to score each candidate's relevance to ``query`` in ``[0.0, 1.0]``.

    Falls back to returning ``hits`` unchanged (truncated to ``top_k``) if the
    model's response isn't parseable JSON, rather than raising — a reranker
    failure shouldn't break retrieval (Bab 10.4).
    """
    from providers.base_provider import GenerationParams
    from providers.provider_factory import create_for_role

    if not hits:
        return hits

    provider = create_for_role(role)
    listing = "\n".join(f"{i}. {hit.text[:300]}" for i, hit in enumerate(hits))
    prompt = (
        f"Query: {query}\n\nKandidat:\n{listing}\n\n"
        "Nilai relevansi tiap kandidat terhadap query dengan skor 0.0-1.0. "
        "Balas HANYA dengan JSON list angka sesuai urutan, contoh: [0.9, 0.2, 0.5]"
    )
    resp = await provider.generate(prompt, GenerationParams(max_tokens=200, temperature=0.0))

    try:
        scores = json.loads(resp.text.strip())
        if not isinstance(scores, list) or len(scores) != len(hits):
            raise ValueError("score list length mismatch")
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("rag.llm_rerank_parse_failed", error=str(exc), raw=resp.text[:200])
        return hits[: top_k or len(hits)]

    scored = [
        KnowledgeHit(entry_id=hit.entry_id, text=hit.text, score=float(score), metadata=hit.metadata)
        for hit, score in zip(hits, scores)
    ]
    scored.sort(key=lambda h: h.score, reverse=True)
    return scored[: top_k or len(scored)]
