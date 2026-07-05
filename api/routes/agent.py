"""Agent API v2 — integrated with Universal Agent tools."""
import uuid
from fastapi import APIRouter, Depends, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List
from agent.core import AIAgent
from core.utils.logger import get_logger
from security.auth import Principal, get_current_principal

router = APIRouter()
logger = get_logger(__name__)


class AgentRequest(BaseModel):
    task: str
    files: list = []
    file_path: str = ""
    model: str = ""
    output_format: str = "auto"
    context: dict = {}
    context: Optional[str] = None
    session_id: Optional[str] = None


@router.post("/run")
async def run_agent(req: AgentRequest, principal: Principal = Depends(get_current_principal)):
    session_id = req.session_id or str(uuid.uuid4())[:8]
    logger.info("Agent v2 run", task=req.task[:80], session=session_id, role=principal.role)
    agent = AIAgent(role=principal.role)
    ctx = req.context or {}
    if req.files:
        ctx["uploaded_files"] = req.files
    if req.file_path:
        ctx["file_path"] = req.file_path
    if req.model:
        ctx["model"] = req.model
    result = await agent.run(task=req.task, context=ctx)
    # Fix: populate output_files dari steps jika kosong
    if not result.get("output_files"):
        import re
        files_found = []
        for step in result.get("steps", []):
            obs = step.get("observation", {})
            if isinstance(obs, dict):
                fp = obs.get("file") or obs.get("path", "")
                if fp and fp not in files_found:
                    files_found.append(fp)
        result["output_files"] = files_found

    return {"session_id": session_id, **result}


@router.get("/tools")
async def list_tools():
    """List all registered tools."""
    agent = AIAgent()
    return {"tools": agent.registry.list_tools()}


@router.get("/reports")
async def list_reports():
    """List generated report files."""
    import os
    reports_dir = os.path.expanduser("~/ai_engine/reports")
    os.makedirs(reports_dir, exist_ok=True)
    files = []
    for f in sorted(os.listdir(reports_dir)):
        path = os.path.join(reports_dir, f)
        files.append({"filename": f, "size": os.path.getsize(path),
                      "ext": f.rsplit(".", 1)[-1] if "." in f else ""})
    return {"files": files, "count": len(files)}
