"""
Chat API — ChatGPT-style conversational endpoint backed by the local Gemma
ChatEngine, with file upload, SSE streaming + tool events, and file download.

Session ownership (Tahap 22, closes the gap Tahap 20 explicitly left open):
every route that touches a `session_id` opts into `get_current_principal`
and calls `_require_session_owner` before doing anything — a 403 before any
work happens, not a stream that starts then errors partway through. Whoever
first touches a `session_id` owns it (`ChatEngine.get_session`/`stream_run`'s
`owner=` kwarg); `GET /sessions` filters to the caller's own instead of
listing everyone's. When `API_KEYS` is unset (dev default), every caller
shares `Principal(api_key="", role="admin")` — every session's owner is
that same empty string, so ownership checks are a no-op and behavior is
identical to before this Tahap, same posture as every other RBAC feature
in this app. `/download/{filename}` is NOT session-scoped (no session_id
in the request at all) — a separate, still-open gap, not silently folded
into this one.
"""
import os
import json
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field

from core.chat.engine import chat_engine, UPLOADS_DIR, REPORTS_DIR
from core.ai.gemma_client import gemma
from core.utils.logger import get_logger
from security.auth import Principal, get_current_principal

router = APIRouter()
logger = get_logger(__name__)


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(..., min_length=1)
    model: Optional[str] = None
    files: List[str] = Field(default_factory=list)  # filenames previously uploaded


def _require_session_owner(session_id: str, principal: Principal) -> None:
    """403 if `session_id` already exists and belongs to someone else.
    A no-op for a session_id that doesn't exist yet (nothing to own) or
    whose owner is None (created before Tahap 22, or by a caller that never
    opted into a role/identity)."""
    session = chat_engine.sessions.get(session_id)
    if session is not None and session.owner is not None and session.owner != principal.api_key:
        raise HTTPException(status_code=403, detail="Sesi ini milik pengguna lain")


@router.post("/upload")
async def upload(
    session_id: str = Form(...),
    files: List[UploadFile] = File(...),
    principal: Principal = Depends(get_current_principal),
):
    """Save uploaded files to the uploads dir; return their server paths."""
    _require_session_owner(session_id, principal)
    saved = []
    for f in files:
        safe = os.path.basename(f.filename or f"file_{uuid.uuid4().hex}")
        dest = os.path.join(UPLOADS_DIR, safe)
        with open(dest, "wb") as out:
            out.write(await f.read())
        saved.append({"filename": safe, "path": dest, "size": os.path.getsize(dest)})
    chat_engine.get_session(session_id, owner=principal.api_key)
    logger.info("files uploaded", session=session_id, count=len(saved))
    return {"session_id": session_id, "files": saved}


@router.post("/stream")
async def stream(req: ChatRequest, principal: Principal = Depends(get_current_principal)):
    """Stream an assistant turn as Server-Sent Events.

    RBAC (Tahap 20): ``principal.role`` is threaded into ``ChatEngine.stream_run``
    so tool-call gates (``TOOL_RISK_ACTIONS``) that were previously inert for
    Chat now apply. When ``API_KEYS`` is unset (dev default), ``principal``
    is always ``role="admin"`` — every gate is a no-op, same as today.

    Session ownership (Tahap 22) is checked here, before ``StreamingResponse``
    is returned — raising inside ``event_source()`` after streaming has
    already started would surface as a broken 200 body, not a clean 403.
    """
    session_id = req.session_id or uuid.uuid4().hex
    _require_session_owner(session_id, principal)
    file_paths = [os.path.join(UPLOADS_DIR, os.path.basename(f)) for f in req.files]

    async def event_source():
        # Tell the client the session id first so it can persist it.
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"
        async for event in chat_engine.stream_run(
            session_id=session_id, user_text=req.message,
            new_files=file_paths, model=req.model, role=principal.role,
            owner=principal.api_key,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/download/{filename}")
async def download(filename: str):
    """Download a produced file from the reports dir."""
    path = os.path.join(REPORTS_DIR, os.path.basename(filename))
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=os.path.basename(path))


@router.get("/sessions")
async def sessions(principal: Principal = Depends(get_current_principal)):
    """Only the caller's own sessions (Tahap 22) — was every session, for everyone."""
    return {"sessions": chat_engine.list_sessions(owner=principal.api_key)}


@router.get("/sessions/{session_id}")
async def session_history(session_id: str, principal: Principal = Depends(get_current_principal)):
    """Return the display history of a session so the UI can re-open it."""
    _require_session_owner(session_id, principal)
    return {"session_id": session_id, "history": chat_engine.get_history(session_id)}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, principal: Principal = Depends(get_current_principal)):
    _require_session_owner(session_id, principal)
    ok = chat_engine.delete_session(session_id)
    return {"deleted": ok}


@router.get("/models")
async def models():
    """List locally available Ollama models for the UI selector."""
    health = await gemma.health_check()
    return {"default": gemma.model, "available": health.get("available_models", [])}
