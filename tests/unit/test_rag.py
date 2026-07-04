"""Unit tests for the RAG pipeline (MASTER_INSTRUCTION.md Bab 29).

The pgvector-backed KnowledgeStore is verified live (see docs/PROGRESS.md) —
mirroring how PostgresConversationStore/PostgresLongTermStore (Tahap 3) are
only unit-tested via their in-memory counterpart. No live network/DB calls
here (Bab 12.3): embedders are hashed-BOW or stubbed.
"""
import json

import pytest

from rag.chunker import chunk_text
from rag.context_builder import build_context
from rag.embeddings import default_embedder, hashed_bow_embedder, hashed_bow_embedder_factory, provider_embedder
from rag.hybrid_search import hybrid_search
from rag.knowledge_store import InMemoryKnowledgeStore, KnowledgeHit
from rag.reranker import llm_rerank, rerank
from rag.retriever import Retriever


# ─── Chunker (Bab 29 step 1) ──────────────────────────────────────────────────

def test_chunk_text_empty_returns_no_chunks():
    assert chunk_text("   ") == []


def test_chunk_text_short_text_single_chunk():
    chunks = chunk_text("halo dunia", chunk_size=800, overlap=100)
    assert len(chunks) == 1
    assert chunks[0].text == "halo dunia"
    assert chunks[0].index == 0


def test_chunk_text_splits_on_whitespace_boundary():
    text = ("kata " * 300).strip()  # 1500 chars, plenty of spaces
    chunks = chunk_text(text, chunk_size=800, overlap=100)
    assert len(chunks) > 1
    for chunk in chunks:
        assert not chunk.text.startswith(" ")
        assert not chunk.text.endswith(" ")


def test_chunk_text_overlap_repeats_content():
    text = "".join(f"{i:04d} " for i in range(300))  # deterministic, no spaces to hide behind
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    # Overlap window: the tail of chunk N should reappear near the head of chunk N+1.
    assert chunks[0].text[-10:] in chunks[1].text


def test_chunk_text_rejects_overlap_ge_chunk_size():
    with pytest.raises(ValueError):
        chunk_text("x" * 100, chunk_size=50, overlap=50)


# ─── Embeddings (Bab 29 step 2) ───────────────────────────────────────────────

async def test_hashed_bow_embedder_is_deterministic_and_sized():
    v1 = await hashed_bow_embedder("harga nikel dunia")
    v2 = await hashed_bow_embedder("harga nikel dunia")
    assert v1 == v2
    assert len(v1) == 512


async def test_hashed_bow_embedder_factory_custom_width():
    embed = hashed_bow_embedder_factory(64)
    vec = await embed("halo")
    assert len(vec) == 64


def test_provider_embedder_rejects_claude():
    with pytest.raises(ValueError):
        provider_embedder("claude")


def test_default_embedder_hashed_explicit(monkeypatch):
    monkeypatch.setattr("api.config.settings.RAG_EMBEDDING_PROVIDER", "hashed")
    monkeypatch.setattr("api.config.settings.RAG_EMBEDDING_DIM", 128)
    embedder = default_embedder()
    assert embedder is not hashed_bow_embedder  # distinct instance at the configured width


async def test_default_embedder_falls_back_when_provider_disabled(monkeypatch):
    monkeypatch.setattr("api.config.settings.RAG_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setattr("api.config.settings.OPENAI_API_KEY", "", raising=False)
    monkeypatch.setattr("api.config.settings.RAG_EMBEDDING_DIM", 32)
    embedder = default_embedder()
    vec = await embedder("test")
    assert len(vec) == 32  # hashed placeholder, not a live provider call


# ─── Knowledge Store (Bab 29 step 3) ──────────────────────────────────────────

async def test_in_memory_knowledge_store_namespaces_are_isolated():
    store = InMemoryKnowledgeStore()
    await store.add("ns1", "a", [1.0, 0.0])
    await store.add("ns2", "b", [1.0, 0.0])
    assert await store.count("ns1") == 1
    assert await store.count("ns2") == 1
    hits = await store.search("ns1", [1.0, 0.0], top_k=5)
    assert len(hits) == 1 and hits[0].text == "a"


async def test_in_memory_knowledge_store_clear():
    store = InMemoryKnowledgeStore()
    await store.add("ns", "a", [1.0])
    await store.clear("ns")
    assert await store.count("ns") == 0
    assert await store.search("ns", [1.0]) == []


async def test_in_memory_knowledge_store_min_score_filters():
    store = InMemoryKnowledgeStore()
    await store.add("ns", "same", [1.0, 0.0])
    await store.add("ns", "orthogonal", [0.0, 1.0])
    hits = await store.search("ns", [1.0, 0.0], min_score=0.5)
    assert [h.text for h in hits] == ["same"]


# ─── Retriever (Bab 29 step 4) ────────────────────────────────────────────────

async def test_retriever_index_and_retrieve_roundtrip():
    store = InMemoryKnowledgeStore()
    r = Retriever("docs", store=store, embedder=hashed_bow_embedder)
    await r.index("harga nikel dunia naik", metadata={"source": "a"})
    await r.index("resep nasi goreng enak", metadata={"source": "b"})
    hits = await r.retrieve("berapa harga nikel", top_k=1)
    assert hits[0].metadata["source"] == "a"


async def test_retriever_index_document_chunks_and_tags_metadata():
    store = InMemoryKnowledgeStore()
    r = Retriever("docs", store=store, embedder=hashed_bow_embedder)
    long_text = ("laporan wilayah tambang " * 100).strip()  # long enough to force >1 chunk

    entry_ids = await r.index_document(long_text, metadata={"source": "laporan.pdf"}, chunk_size=200, overlap=20)

    assert len(entry_ids) > 1
    assert await store.count("docs") == len(entry_ids)
    hits = await r.retrieve("laporan wilayah tambang", top_k=len(entry_ids))
    for hit in hits:
        assert hit.metadata["source"] == "laporan.pdf"
        assert "chunk_index" in hit.metadata


# ─── Hybrid Search (Bab 29 step 5) ────────────────────────────────────────────

def test_hybrid_search_boosts_exact_keyword_match():
    hits = [
        KnowledgeHit(entry_id="1", text="dokumen umum tentang tambang", score=0.9),
        KnowledgeHit(entry_id="2", text="sertifikat IUP-2024-0087 milik PT Jaya", score=0.4),
    ]
    blended = hybrid_search("IUP-2024-0087", hits, alpha=0.3)
    assert blended[0].entry_id == "2"


def test_hybrid_search_empty_hits():
    assert hybrid_search("query", []) == []


# ─── Reranker (Bab 29 step 6) ─────────────────────────────────────────────────

def test_rerank_boosts_code_like_token_matches():
    hits = [
        KnowledgeHit(entry_id="1", text="dokumen umum tentang tambang", score=0.5),
        KnowledgeHit(entry_id="2", text="nomor sertifikat iup-2024-0087 terlampir", score=0.45),
    ]
    reranked = rerank("cek iup-2024-0087 dong", hits)
    assert reranked[0].entry_id == "2"


def test_rerank_no_code_tokens_returns_hits_unchanged():
    hits = [KnowledgeHit(entry_id="1", text="a", score=0.5)]
    assert rerank("pertanyaan biasa", hits) == hits


async def test_llm_rerank_parses_scores_and_sorts(monkeypatch):
    class StubProvider:
        async def generate(self, prompt, params):
            class R:
                text = json.dumps([0.1, 0.9])
            return R()

    monkeypatch.setattr("providers.provider_factory.create_for_role", lambda role: StubProvider())
    hits = [
        KnowledgeHit(entry_id="1", text="a", score=0.5),
        KnowledgeHit(entry_id="2", text="b", score=0.4),
    ]
    reranked = await llm_rerank("query", hits)
    assert [h.entry_id for h in reranked] == ["2", "1"]


async def test_llm_rerank_falls_back_on_bad_json(monkeypatch):
    class StubProvider:
        async def generate(self, prompt, params):
            class R:
                text = "not json"
            return R()

    monkeypatch.setattr("providers.provider_factory.create_for_role", lambda role: StubProvider())
    hits = [KnowledgeHit(entry_id="1", text="a", score=0.5)]
    reranked = await llm_rerank("query", hits)
    assert reranked == hits


async def test_llm_rerank_empty_hits_short_circuits():
    assert await llm_rerank("query", []) == []


# ─── Context Builder (Bab 29 step 7) ──────────────────────────────────────────

def test_build_context_includes_citations():
    hits = [KnowledgeHit(entry_id="e1", text="isi dokumen", score=0.9, metadata={"source": "doc.pdf"})]
    ctx = build_context(hits, max_chars=4000)
    assert "[1] doc.pdf" in ctx.text
    assert "isi dokumen" in ctx.text
    assert not ctx.truncated
    assert ctx.included == hits


def test_build_context_truncates_under_budget():
    hits = [
        KnowledgeHit(entry_id="1", text="a" * 50, score=0.9, metadata={"source": "s1"}),
        KnowledgeHit(entry_id="2", text="b" * 50, score=0.8, metadata={"source": "s2"}),
    ]
    ctx = build_context(hits, max_chars=60)
    assert len(ctx.included) == 1
    assert ctx.truncated is True


def test_build_context_no_hits():
    ctx = build_context([], max_chars=4000)
    assert ctx.text == ""
    assert ctx.included == []
    assert not ctx.truncated
