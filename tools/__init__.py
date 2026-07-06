"""New infrastructure package for Project Workspace (Bab 69 / ADR-0005, Tahap 19).

Not to be confused with `agent/tools/` (a protected folder, Bab 45.1) — that
package holds the Chat/Agent tool registry (readers/writers/analyzers/GIS/
images). This package holds filesystem-access primitives that `workspace/`
uses to read Workspace Folder content safely (Root Restriction, Bab 69.6).

The SSOT docs (`MASTER_INSTRUCTION.md` Bab 69.11) describe extending
`tools/adapters/filesystem.py` "yang sudah ada" (already existing) — but no
`tools/` package existed anywhere in this repo before this Tahap. Created
fresh here, sibling to `registry/`/`rag/`/`memory/`/`agent/` (Bab 5), not a
violation of Bab 45.1 (which names `agent/tools/` specifically, not this).
"""
