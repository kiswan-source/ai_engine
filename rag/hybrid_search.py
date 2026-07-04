"""Hybrid Search (MASTER_INSTRUCTION.md Bab 29 step 5) — semantic + keyword.

Bab 29 rule 2: keyword/BM25 search is prioritized over pure vector search for
domains with specific technical/legal terms (certificate numbers, article
numbers, IUP codes) — embeddings alone can rate a chunk with the right code
lower than one that's merely topically similar. This blends a BM25 score,
computed over the semantic candidate set itself (no separate inverted index,
no new dependency — Bab 45.3), with each hit's existing vector score.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .knowledge_store import KnowledgeHit

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _bm25_scores(query_tokens: list[str], doc_tokens_list: list[list[str]], k1: float = 1.5, b: float = 0.75) -> list[float]:
    """Okapi BM25 over ``doc_tokens_list`` (the candidate set, not the full corpus)."""
    n_docs = len(doc_tokens_list)
    if n_docs == 0 or not query_tokens:
        return [0.0] * n_docs

    avg_len = sum(len(doc) for doc in doc_tokens_list) / n_docs
    doc_freq: Counter = Counter()
    for doc in doc_tokens_list:
        doc_freq.update(set(doc))

    scores = []
    for doc in doc_tokens_list:
        term_freq = Counter(doc)
        doc_len = len(doc)
        score = 0.0
        for term in query_tokens:
            freq = term_freq.get(term, 0)
            if freq == 0:
                continue
            idf = math.log(1 + (n_docs - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
            denom = freq + k1 * (1 - b + b * doc_len / avg_len)
            score += idf * (freq * (k1 + 1)) / denom
        scores.append(score)
    return scores


def hybrid_search(query: str, semantic_hits: list[KnowledgeHit], alpha: float | None = None) -> list[KnowledgeHit]:
    """Blend ``semantic_hits``' vector scores with BM25 keyword scores.

    Args:
        alpha: Weight of the semantic score (``1.0`` = pure semantic, ``0.0``
            = pure keyword); defaults to ``settings.RAG_HYBRID_ALPHA``.
    """
    from api.config import settings

    alpha = settings.RAG_HYBRID_ALPHA if alpha is None else alpha
    if not semantic_hits:
        return []

    query_tokens = _tokenize(query)
    doc_tokens = [_tokenize(hit.text) for hit in semantic_hits]
    bm25 = _bm25_scores(query_tokens, doc_tokens)
    peak = max(bm25) if bm25 else 0.0
    normalized_bm25 = [score / peak if peak > 0 else 0.0 for score in bm25]

    blended = [
        KnowledgeHit(
            entry_id=hit.entry_id,
            text=hit.text,
            score=alpha * hit.score + (1 - alpha) * keyword_score,
            metadata=hit.metadata,
        )
        for hit, keyword_score in zip(semantic_hits, normalized_bm25)
    ]
    blended.sort(key=lambda h: h.score, reverse=True)
    return blended
