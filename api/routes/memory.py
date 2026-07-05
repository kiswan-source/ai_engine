"""Memory API — exposes `memory/` tiers (Tahap 3, Bab 22) over HTTP, scoped
to a session_id, for the Memory page (AI_WORKSPACE_ARCHITECTURE.md §2). Not
a protected folder (Bab 45.1).

Real gap acknowledged (docs/PROGRESS.md Tahap 12): `core/chat/engine.py`
never writes to any `memory/` tier, so every response here is empty for any
real chat session_id today — wired ahead of that integration by deliberate
choice (confirmed with the user), not a bug to be silently papered over.

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
"""
from fastapi import APIRouter

from memory.memory_manager import build_memory_manager

router = APIRouter()
_memory = build_memory_manager()


@router.get("/{session_id}")
async def get_session_memory(session_id: str):
    """Everything remembered under `session_id` across the four user-facing tiers."""
    return {
        "session_id": session_id,
        "working": await _memory.working.get_all(session_id),
        "conversation_history": await _memory.conversation.get_history(session_id),
        "summary": await _memory.summary.get_summary(session_id),
        "long_term": await _memory.long_term.recall_all(session_id),
    }


@router.delete("/{session_id}/working/{key}")
async def forget_working(session_id: str, key: str):
    await _memory.working.forget(session_id, key)
    return {"deleted": True}


@router.delete("/{session_id}/long-term/{key}")
async def forget_long_term(session_id: str, key: str):
    await _memory.long_term.forget(session_id, key)
    return {"deleted": True}


@router.delete("/{session_id}/conversation")
async def clear_conversation(session_id: str):
    """Whole-session only — ConversationMemory has no per-message delete (Bab 22)."""
    await _memory.conversation.clear(session_id)
    return {"cleared": True}


@router.delete("/{session_id}/summary")
async def clear_summary(session_id: str):
    await _memory.summary.clear(session_id)
    return {"cleared": True}
