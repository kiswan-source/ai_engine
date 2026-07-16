"""Cross-session memory tools exposed to the Chat Engine's tool-calling loop
(Fase 3, DCF v5 mandate "Memory Intelligence Evolution").

Owner-chosen design (Fase 3): only ``remember_fact``/``recall_facts`` cross
session boundaries — namespaced by the caller's OWNER identity, never
``workspace_id`` (Project Workspaces have multi-user membership, so
namespacing by workspace would leak one member's remembered facts to every
other member with no consent — exactly the "kebocoran memori lintas sesi"
risk the v5 roadmap flagged as Fase 3's main risk). The model calls these
only when the user explicitly asks to be remembered ("ingat bahwa...",
"simpan preferensi saya") — this is NOT automatic per-turn promotion.
Automatic, session-scoped memory (working/conversation/summary) is wired
directly in ``core/chat/engine.py`` instead, not exposed as tools.

``owner`` is always injected by ``ChatEngine._run_tool`` from the session's
authenticated caller — never taken from the model's own arguments (same
rule Tahap 23 established for ``workspace_id``, see
``agent/tools/workspace_reader.py``). ``owner=None`` (no authenticated
caller, e.g. dev with blank API_KEYS) maps to a shared "anonymous"
namespace — same trade-off already accepted elsewhere in this codebase for
that configuration, not a new risk introduced here.

Postgres-backend note: when ``MEMORY_PERSISTENT_BACKEND=postgres``
(``.env.example``'s recommended production value), these functions build a
FRESH engine/session-factory per call rather than reuse
``memory.memory_manager.get_shared_memory_manager()`` — the same
asyncpg-event-loop-affinity constraint ``agent/tools/workspace_reader.py``
already documents: this module's functions run via
``ToolRegistry.execute`` -> ``asyncio.to_thread`` -> ``asyncio.run()``, a
different event loop each call, which an asyncpg connection can't be
reused across. The in-memory backend (dev/CI default) has no such
constraint — a plain dict doesn't care what loop touches it — so it reuses
the shared manager's store directly, which is what keeps it consistent
with what ``core/chat/engine.py``/``api/routes/memory.py`` see.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from memory.long_term_memory import LongTermMemory, PostgresLongTermStore


def _namespace_for(owner: Optional[str]) -> str:
    return f"owner:{owner or 'anonymous'}"


def _long_term_memory():
    """Return ``(LongTermMemory, disposable_engine_or_None)`` for the
    configured persistent backend — caller must dispose the engine, if any."""
    from api.config import settings

    if settings.MEMORY_PERSISTENT_BACKEND.lower() == "postgres":
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        engine = create_async_engine(settings.DATABASE_URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        return LongTermMemory(PostgresLongTermStore(session_factory=factory)), engine

    from memory.memory_manager import get_shared_memory_manager

    return get_shared_memory_manager().long_term, None


def remember_fact(key: str, value: str, owner: Optional[str] = None) -> Dict[str, Any]:
    """Simpan satu fakta/preferensi permanen untuk ``owner``, dapat diambil
    lagi lintas sesi chat manapun. ``owner`` selalu disuntik oleh
    `ChatEngine._run_tool` — lihat modul docstring."""

    async def _run():
        memory, engine = _long_term_memory()
        try:
            await memory.remember(_namespace_for(owner), key, value)
            return {"success": True, "key": key}
        finally:
            if engine is not None:
                await engine.dispose()

    return asyncio.run(_run())


def recall_facts(owner: Optional[str] = None) -> Dict[str, Any]:
    """Ambil semua fakta yang pernah diminta untuk diingat oleh ``owner``
    ini. ``owner`` selalu disuntik oleh `ChatEngine._run_tool`."""

    async def _run():
        memory, engine = _long_term_memory()
        try:
            facts = await memory.recall_all(_namespace_for(owner))
            return {"success": True, "facts": facts}
        finally:
            if engine is not None:
                await engine.dispose()

    return asyncio.run(_run())
