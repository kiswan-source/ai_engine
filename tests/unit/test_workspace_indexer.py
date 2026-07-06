"""Unit tests for workspace/indexer.py (Bab 69.10 — Workspace as a RAG Source)."""
from rag.embeddings import hashed_bow_embedder
from rag.knowledge_store import InMemoryKnowledgeStore
from rag.retriever import Retriever
from tools.adapters.filesystem import FilesystemAdapter
from workspace.indexer import RAG_NAMESPACE, index_folder


def _retriever():
    return Retriever(namespace=RAG_NAMESPACE, store=InMemoryKnowledgeStore(), embedder=hashed_bow_embedder)


async def test_index_folder_indexes_text_files_and_skips_images(tmp_path):
    (tmp_path / "report.txt").write_text("mining feasibility study for site alpha")
    (tmp_path / "site.png").write_bytes(b"\x89PNG-fake")
    adapter = FilesystemAdapter(tmp_path)
    retriever = _retriever()

    chunks = await index_folder(adapter, workspace_id="ws-1", folder_id="f-1", retriever=retriever)

    assert chunks >= 1
    hits = await retriever.retrieve("mining feasibility study")
    assert any(h.metadata.get("source") == "workspace" for h in hits)
    assert any(h.metadata.get("workspace_id") == "ws-1" for h in hits)
    assert any(h.metadata.get("folder_id") == "f-1" for h in hits)


async def test_index_folder_skips_unsupported_extensions(tmp_path):
    (tmp_path / "notes.xyz").write_text("unsupported extension content")
    adapter = FilesystemAdapter(tmp_path)
    retriever = _retriever()

    chunks = await index_folder(adapter, workspace_id="ws-2", folder_id="f-2", retriever=retriever)

    assert chunks == 0


async def test_index_folder_skips_unparseable_file_without_raising(tmp_path):
    # A .pdf that isn't a real PDF — pypdf will fail to parse it; the indexer
    # must skip it (logged), not propagate the exception.
    (tmp_path / "broken.pdf").write_bytes(b"not a real pdf")
    adapter = FilesystemAdapter(tmp_path)
    retriever = _retriever()

    chunks = await index_folder(adapter, workspace_id="ws-3", folder_id="f-3", retriever=retriever)

    assert chunks == 0
