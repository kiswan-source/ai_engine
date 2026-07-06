"""Project Workspace domain module (MASTER_INSTRUCTION.md Bab 69, ADR-0005, Tahap 19).

Sibling to `registry/`/`rag/`/`memory/` (Bab 5) — not a protected folder.
Depends on `tools/adapters/filesystem.py` for actual disk access (Hexagonal
Architecture, Bab 4.2: domain logic here, infrastructure there) and on
`rag/retriever.py` for indexing, but never on `api/` (that would invert the
dependency direction — routes call into this module, not the other way).
"""
