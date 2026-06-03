"""
Chat API — ChatGPT-style conversational endpoint backed by the local Gemma
ChatEngine, with file upload, SSE streaming + tool events, and file download.
"""
import os
import json
import uuid
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field

from core.chat.engine import chat_engine, UPLOADS_DIR, REPORTS_DIR
from core.ai.gemma_client import gemma
from core.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(..., min_length=1)
    model: Optional[str] = None
    files: List[str] = Field(default_factory=list)  # filenames previously uploaded


@router.post("/upload")
async def upload(session_id: str = Form(...), files: List[UploadFile] = File(...)):
    """Save uploaded files to the uploads dir; return their server paths."""
    saved = []
    for f in files:
        safe = os.path.basename(f.filename or f"file_{uuid.uuid4().hex}")
        dest = os.path.join(UPLOADS_DIR, safe)
        with open(dest, "wb") as out:
            out.write(await f.read())
        saved.append({"filename": safe, "path": dest, "size": os.path.getsize(dest)})
    chat_engine.get_session(session_id)
    logger.info("files uploaded", session=session_id, count=len(saved))
    return {"session_id": session_id, "files": saved}


@router.post("/stream")
async def stream(req: ChatRequest):
    """Stream an assistant turn as Server-Sent Events."""
    session_id = req.session_id or uuid.uuid4().hex
    file_paths = [os.path.join(UPLOADS_DIR, os.path.basename(f)) for f in req.files]

    async def event_source():
        # Tell the client the session id first so it can persist it.
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"
        async for event in chat_engine.stream_run(
            session_id=session_id, user_text=req.message,
            new_files=file_paths, model=req.model,
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
async def sessions():
    return {"sessions": chat_engine.list_sessions()}


@router.get("/sessions/{session_id}")
async def session_history(session_id: str):
    """Return the display history of a session so the UI can re-open it."""
    return {"session_id": session_id, "history": chat_engine.get_history(session_id)}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    ok = chat_engine.delete_session(session_id)
    return {"deleted": ok}


@router.get("/models")
async def models():
    """List locally available Ollama models for the UI selector."""
    health = await gemma.health_check()
    return {"default": gemma.model, "available": health.get("available_models", [])}
