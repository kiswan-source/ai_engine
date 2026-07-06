"""Integration tests for /api/v1/knowledge/* — the first route in the app to
actually exercise `db.connection.get_session()` as a real dependency.

Uses an in-memory SQLite engine instead of Postgres (Bab 12.3 — CI has no
live services) via FastAPI's `dependency_overrides`, creating only the
`documents` table: `Base.metadata` also has `VectorEmbedding`, whose column
uses the Postgres-only `pgvector` type and would fail `create_all()` on
SQLite if included.

`api.routes.knowledge`'s module-level `_retriever` singleton is swapped per
test for one backed by an explicit `InMemoryKnowledgeStore` (same pattern
`test_orchestrator_api.py` uses for `_orchestrator`) — this dev box has
`VECTOR_BACKEND=pgvector` configured (Tahap 5) in `.env`, and `_retriever`
is built once at module import time, before any per-test monkeypatch of
`settings` could take effect. Without this override the route would reuse
whatever real Postgres-backed store got constructed at import, open a real
asyncpg connection outside pytest-asyncio's per-test event loop, and fail
teardown with a "different loop" error. `InMemoryKnowledgeStore` is what CI
actually exercises (no `.env` there), so pinning it here keeps the test
hermetic (Bab 12.3) rather than depending on whichever backend happens to
be configured locally.

Also pins `embedder=hashed_bow_embedder` explicitly (Tahap 40 fix) —
`Retriever.__init__`'s default is `embedder or default_embedder()`, and
`default_embedder()` reads `RAG_EMBEDDING_PROVIDER` from `settings` at
call time, same as the store did. Without this override, any dev box with
a real `OPENAI_API_KEY` configured (this one has one, Tahap 4/provider
verification) makes real, slow, sometimes-flaky network calls to OpenAI's
embedding endpoint on every ingest/search in this "isolated" test — caught
live via `ss -tnp` showing a real HTTPS connection from the pytest
process (Tahap 39 RWX-storage verification's incidental discovery).
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.connection import get_session
from db.models import Document
from rag.embeddings import hashed_bow_embedder
from rag.knowledge_store import InMemoryKnowledgeStore
from rag.retriever import Retriever


@pytest.fixture(autouse=True)
def _isolated_retriever(monkeypatch):
    import api.routes.knowledge as route

    monkeypatch.setattr(
        route, "_retriever",
        Retriever(namespace=route.RAG_NAMESPACE, store=InMemoryKnowledgeStore(), embedder=hashed_bow_embedder),
    )


@pytest.fixture
async def app():
    from api.main import app as _app

    yield _app


@pytest.fixture
async def sqlite_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Document.metadata.create_all, tables=[Document.__table__])
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def client(app, sqlite_session_factory):
    async def _override_get_session():
        async with sqlite_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_list_documents_empty(client):
    res = await client.get("/api/v1/knowledge/documents")
    assert res.status_code == 200
    assert res.json() == {"documents": []}


async def test_ingest_and_list_document(client):
    ingest_res = await client.post(
        "/api/v1/knowledge/documents",
        json={"title": "Circuit Breaker", "text": "Melindungi sistem dari provider yang gagal berulang."},
    )
    assert ingest_res.status_code == 200
    body = ingest_res.json()
    assert body["title"] == "Circuit Breaker"
    assert body["chunks_indexed"] >= 1

    list_res = await client.get("/api/v1/knowledge/documents")
    docs = list_res.json()["documents"]
    assert len(docs) == 1
    assert docs[0]["id"] == body["id"]
    assert docs[0]["word_count"] == 7


async def test_search_returns_ingested_text(client):
    await client.post(
        "/api/v1/knowledge/documents",
        json={"title": "Circuit Breaker", "text": "Circuit breaker melindungi sistem dari provider gagal."},
    )

    res = await client.get("/api/v1/knowledge/search", params={"q": "provider gagal"})
    assert res.status_code == 200
    hits = res.json()["hits"]
    assert len(hits) >= 1
    assert "provider" in hits[0]["text"]


async def test_delete_document_removes_from_list(client):
    ingest_res = await client.post(
        "/api/v1/knowledge/documents", json={"title": "Sementara", "text": "isi apa saja"}
    )
    doc_id = ingest_res.json()["id"]

    delete_res = await client.delete(f"/api/v1/knowledge/documents/{doc_id}")
    assert delete_res.status_code == 200
    assert delete_res.json() == {"deleted": True}

    list_res = await client.get("/api/v1/knowledge/documents")
    assert list_res.json()["documents"] == []


async def test_delete_unknown_document_404(client):
    res = await client.delete("/api/v1/knowledge/documents/does-not-exist")
    assert res.status_code == 404
