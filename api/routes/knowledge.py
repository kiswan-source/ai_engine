"""Knowledge API — first-ever HTTP wiring for `rag/` (Tahap 5, Bab 29). Not a
protected folder (Bab 45.1).

Real gap this closes (docs/PROGRESS.md Tahap 12): `rag/`'s `KnowledgeStore`
has no "list all documents" method (only `add`/`search`/`count`/`clear` by
namespace), so there was no way to show a user what's in the knowledge base.
Reuses the existing (until now unused) `db.models.Document` table as a
manifest — `api/routes/dokumen.py` defines this model but never writes to
it, and nothing else does either. `content_text` here holds the pasted text
verbatim (not the mining-document generator's parsed-file text); this table
was simply the closest fit for "one row per ingested source", not a
repurposing of an unrelated feature.

Ingest UX is paste-text-only for now (confirmed choice, not upload/OCR) —
`Retriever(namespace=RAG_NAMESPACE).index_document()` handles chunking.
Deleting a document removes its manifest row only: `KnowledgeStore` has no
delete-by-metadata/by-document method, so its chunks remain searchable in
the vector store after the manifest entry is gone — a known limitation,
not silently hidden.

Uses `db.connection.get_session` as a real `Depends()` for the first time
in the app (previously defined but never wired to a route).

One module-level `Retriever` (same singleton pattern as
`api/routes/orchestrator.py`'s `Orchestrator()` and
`api/routes/memory.py`'s `MemoryManager`) — `Retriever(namespace=...)`
with no explicit `store` builds a fresh `KnowledgeStore` on every call, and
the in-memory backend (the default, and what CI actually exercises) is
pure in-process state: a per-request `Retriever` would forget everything
between requests. Only invisible in ad-hoc local testing because this dev
box has `VECTOR_BACKEND=pgvector` configured, which persists to real
Postgres regardless of which Python object touches it.

Authentication (Tahap 26): every route now requires
`Depends(get_current_principal)` — same posture as `api/routes/files.py`
(Tahap 25): authentication, not per-user ownership. There's no owner
concept for a `Document` (the knowledge base is shared across every
caller, same as it always has been) — this closes "anyone, no key at all"
without pretending to be a finer-grained model that doesn't exist yet.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.connection import get_session
from db.models import Document
from rag.retriever import Retriever
from security.auth import Principal, get_current_principal

router = APIRouter()

RAG_NAMESPACE = "rag:documents"
_retriever = Retriever(namespace=RAG_NAMESPACE)


class IngestRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    text: str = Field(..., min_length=1)


class DocumentSummary(BaseModel):
    id: str
    title: str
    word_count: int | None
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/documents")
async def ingest_document(
    req: IngestRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    doc = Document(
        filename=req.title,
        doc_type="knowledge",
        content_text=req.text,
        word_count=len(req.text.split()),
    )
    session.add(doc)
    await session.flush()

    chunk_ids = await _retriever.index_document(req.text, metadata={"document_id": doc.id, "title": req.title})
    await session.commit()

    return {"id": doc.id, "title": doc.filename, "chunks_indexed": len(chunk_ids)}


@router.get("/documents")
async def list_documents(
    session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal)
):
    result = await session.execute(select(Document).where(Document.doc_type == "knowledge").order_by(Document.created_at.desc()))
    docs = result.scalars().all()
    return {
        "documents": [
            {"id": d.id, "title": d.filename, "word_count": d.word_count, "created_at": d.created_at}
            for d in docs
        ]
    }


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    doc = await session.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    await session.delete(doc)
    await session.commit()
    return {"deleted": True}


@router.get("/search")
async def search_knowledge(q: str, principal: Principal = Depends(get_current_principal)):
    hits = await _retriever.retrieve(q)
    return {"hits": [{"entry_id": h.entry_id, "text": h.text, "score": h.score, "metadata": h.metadata} for h in hits]}
