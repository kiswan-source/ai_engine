"""Integration tests for Knowledge API authentication (Tahap 26) — closes
"anyone, no key at all" on `/api/v1/knowledge/*`. Authentication only, not
per-user ownership: `Document` has no owner concept (the knowledge base is
shared across every caller, same as it always has been) — same posture as
`api/routes/files.py` (Tahap 25).

Same isolated-retriever + sqlite pattern as `test_knowledge_api.py` (which
deliberately runs with no `API_KEYS` to prove the ingest/search plumbing
itself) — kept in a separate file rather than retrofitting headers onto
every call there. Also pins `embedder=hashed_bow_embedder` for the same
reason as that file (Tahap 40 fix) — see its docstring for the full story.
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
def _api_keys(monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "anykey:user")


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


def _as(key: str) -> dict:
    return {"X-API-Key": key}


async def test_ingest_requires_auth(client):
    res = await client.post("/api/v1/knowledge/documents", json={"title": "T", "text": "isi"})
    assert res.status_code == 401


async def test_ingest_with_valid_key(client):
    res = await client.post(
        "/api/v1/knowledge/documents", json={"title": "T", "text": "isi"}, headers=_as("anykey")
    )
    assert res.status_code == 200


async def test_list_documents_requires_auth(client):
    res = await client.get("/api/v1/knowledge/documents")
    assert res.status_code == 401


async def test_delete_document_requires_auth(client):
    res = await client.delete("/api/v1/knowledge/documents/some-id")
    assert res.status_code == 401


async def test_search_requires_auth(client):
    res = await client.get("/api/v1/knowledge/search", params={"q": "apapun"})
    assert res.status_code == 401


async def test_search_with_valid_key(client):
    res = await client.get("/api/v1/knowledge/search", params={"q": "apapun"}, headers=_as("anykey"))
    assert res.status_code == 200


async def test_no_api_keys_configured_behaves_as_before(client, monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "")
    res = await client.get("/api/v1/knowledge/documents")
    assert res.status_code == 200
