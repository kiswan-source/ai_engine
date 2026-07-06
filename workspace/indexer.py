"""Workspace Index (Bab 69.10) — feeds document-classified files under a
Workspace Folder into the same RAG pipeline `api/routes/knowledge.py` uses
for pasted-text ingestion, so Knowledge search (`GET /api/v1/knowledge/search`)
finds Workspace content too instead of maintaining a second, fragmented index.

Text extraction reuses `agent/tools/readers.py` (the same parsers Chat/Agent
already use for PDF/TXT/DOCX/CSV/JSON) rather than re-implementing PDF/DOCX
parsing here — those readers cap extracted text at 10,000 chars for PDF/TXT/
JSON (a limit inherited from their original "keep chat context small" design,
not something this Tahap introduces); very large source documents will only
be partially indexed until that cap is revisited.

``RAG_NAMESPACE`` is intentionally a local literal, not an import from
`api/routes/knowledge.py` — this module (domain, `workspace/`) must not
depend on `api/` (interface layer); the two constants are kept manually in
sync (both read ``"rag:documents"``, the module-level default before any
config override).
"""
from __future__ import annotations

import os

from agent.tools.readers import read_csv, read_docx, read_json, read_pdf, read_txt
from core.utils.logger import get_logger
from rag.retriever import Retriever
from tools.adapters.filesystem import FilesystemAdapter

logger = get_logger(__name__)

RAG_NAMESPACE = "rag:documents"

_READERS = {
    "pdf": read_pdf,
    "txt": read_txt,
    "md": read_txt,
    "log": read_txt,
    "docx": read_docx,
    "doc": read_docx,
    "csv": read_csv,
    "json": read_json,
}


def _extract_text(adapter: FilesystemAdapter, relative_path: str) -> str | None:
    ext = os.path.splitext(relative_path)[1].lower().lstrip(".")
    reader = _READERS.get(ext)
    if reader is None:
        return None
    result = reader(str(adapter.absolute_path(relative_path)))
    if "error" in result:
        logger.warning("workspace.index.read_failed", path=relative_path, error=result["error"])
        return None
    return result.get("text") or None


async def index_folder(
    adapter: FilesystemAdapter,
    workspace_id: str,
    folder_id: str,
    retriever: Retriever | None = None,
) -> int:
    """Index every document-classified file under ``adapter``'s root.

    Returns the number of chunks indexed. Skips files with an unsupported
    extension or that fail to parse (logged, not raised — one bad file
    should not fail the whole Workspace index run).
    """
    retriever = retriever or Retriever(namespace=RAG_NAMESPACE)
    scan = adapter.scan()
    chunks_indexed = 0
    for f in scan.files:
        if f.category != "document":
            continue
        text = _extract_text(adapter, f.relative_path)
        if not text:
            continue
        chunk_ids = await retriever.index_document(
            text,
            metadata={
                "source": "workspace",
                "workspace_id": workspace_id,
                "folder_id": folder_id,
                "path": f.relative_path,
            },
        )
        chunks_indexed += len(chunk_ids)
    logger.info("workspace.index.folder_done", folder_id=folder_id, chunks=chunks_indexed)
    return chunks_indexed
