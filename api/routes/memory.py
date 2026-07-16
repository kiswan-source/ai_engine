"""Memory API — exposes `memory/` tiers (Tahap 3, Bab 22) over HTTP, scoped
to a session_id, for the Memory page (AI_WORKSPACE_ARCHITECTURE.md §2). Not
a protected folder (Bab 45.1).

Fase 3 (DCF v5 mandate, "Memory Intelligence Evolution"): `core/chat/engine.py`
now writes working/conversation/summary per turn, keyed by the same
session_id this module reads — using `memory.memory_manager.get_shared_memory_manager()`,
the SAME manager instance `core/chat/engine.py` holds, not a private
`build_memory_manager()` call (that would leave the in-memory dev/CI
backends as disconnected islands that never see the Chat Engine's writes —
see that function's docstring). `long_term` here stays whatever it was
before this Tahap: nothing in `core/chat/engine.py` writes to it under a
plain `session_id` namespace — the new `remember_fact`/`recall_facts` tools
(Fase 3) write under an `owner:<id>` namespace instead (deliberately NOT
session-scoped, since remembering across sessions is the whole point), so
they don't show up here; a session-scoped long_term view staying empty is
expected, not a regression.

Scoped to the four tiers where "one key = one session's data" makes sense:
working, conversation, summary, long_term. Reflection memory is keyed by
*agent role*, not session — an internal self-improvement mechanism, not
user-facing (same reasoning `telemetry/monitoring.py`'s Memory Dashboard
uses to exclude it). Vector memory is search-only (no plain listing) —
excluded too.

One module-level `MemoryManager`, same singleton pattern as
`api/routes/orchestrator.py`'s `Orchestrator()` — a fresh instance per
request would lose all data between requests for the default in-memory
backends.

Session ownership (Tahap 26, closes a gap `docs/PROGRESS.md` flagged as
risky since Tahap 12: "siapa pun yang tahu session_id orang lain bisa
membaca/menghapus memori sesi itu tanpa otorisasi apa pun"): every route
here reuses `api/routes/chat.py::_require_session_owner` directly — this
module's `session_id` is meant to be the same session a `core/chat/engine.py`
`Session` is keyed by, so the same ownership check Tahap 22 already built
applies unchanged, rather than inventing a second mechanism. A `session_id`
ChatEngine has never seen (still the common case per the gap above) has no
owner recorded, so the check is a no-op for it — identical behavior to
before this Tahap for that case; only a session with a *recorded* owner
now rejects a different caller.
"""
from fastapi import APIRouter, Depends

from memory.memory_manager import get_shared_memory_manager
from security.auth import Principal, get_current_principal
from api.routes.chat import _require_session_owner

router = APIRouter()
_memory = get_shared_memory_manager()


@router.get("/{session_id}")
async def get_session_memory(session_id: str, principal: Principal = Depends(get_current_principal)):
    """Everything remembered under `session_id` across the four user-facing tiers."""
    _require_session_owner(session_id, principal)
    return {
        "session_id": session_id,
        "working": await _memory.working.get_all(session_id),
        "conversation_history": await _memory.conversation.get_history(session_id),
        "summary": await _memory.summary.get_summary(session_id),
        "long_term": await _memory.long_term.recall_all(session_id),
    }


@router.delete("/{session_id}/working/{key}")
async def forget_working(session_id: str, key: str, principal: Principal = Depends(get_current_principal)):
    _require_session_owner(session_id, principal)
    await _memory.working.forget(session_id, key)
    return {"deleted": True}


@router.delete("/{session_id}/long-term/{key}")
async def forget_long_term(session_id: str, key: str, principal: Principal = Depends(get_current_principal)):
    _require_session_owner(session_id, principal)
    await _memory.long_term.forget(session_id, key)
    return {"deleted": True}


@router.delete("/{session_id}/conversation")
async def clear_conversation(session_id: str, principal: Principal = Depends(get_current_principal)):
    """Whole-session only — ConversationMemory has no per-message delete (Bab 22)."""
    _require_session_owner(session_id, principal)
    await _memory.conversation.clear(session_id)
    return {"cleared": True}


@router.delete("/{session_id}/summary")
async def clear_summary(session_id: str, principal: Principal = Depends(get_current_principal)):
    _require_session_owner(session_id, principal)
    await _memory.summary.clear(session_id)
    return {"cleared": True}
