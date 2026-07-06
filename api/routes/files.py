"""File serving & upload endpoints untuk Agent.

Tahap 25 — closes the gap Tahap 24 found (and confirmed live) while
verifying `/api/v1/chat/download`'s new ownership check: this router served
the exact same `reports/`/`uploads/` directories with zero authentication
at all, a working bypass of that protection. Every route here now opts into
`Depends(get_current_principal)`, the same posture every other RBAC'd route
in this app already uses (open when `API_KEYS` is unset, the dev default;
401 on a missing/invalid key once it's configured). This is authentication,
not per-user ownership like `/api/v1/chat/download` (Tahap 24) — there's no
session concept here at all, so any authenticated caller can still see any
file in these directories. A narrower guarantee than Chat's, but a real
improvement over "anyone on the network, no key needed."

Also fixes a real path-traversal bug found in the same pass: `filename`/
`file.filename` were joined into `REPORTS_DIR`/`UPLOADS_DIR` with no
`os.path.basename()` sanitization at all — `agent/tools/writers.py`/
`core/chat/engine.py` already treat that as the standard defense here, this
router just never had it.
"""
import os
import shutil
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from security.auth import Principal, get_current_principal

router = APIRouter()
REPORTS_DIR = os.path.expanduser("~/ai_engine/reports")
UPLOADS_DIR = os.path.expanduser("~/ai_engine/uploads")
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)


@router.get("/reports/{filename}")
async def download_report(filename: str, principal: Principal = Depends(get_current_principal)):
    """Download file hasil agent."""
    safe_name = os.path.basename(filename)
    path = os.path.join(REPORTS_DIR, safe_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=safe_name)


@router.get("/reports")
async def list_reports(principal: Principal = Depends(get_current_principal)):
    """List semua file di folder reports."""
    files = []
    for f in sorted(os.listdir(REPORTS_DIR)):
        path = os.path.join(REPORTS_DIR, f)
        files.append({
            "filename": f,
            "size": os.path.getsize(path),
            "ext": f.rsplit(".", 1)[-1] if "." in f else "",
        })
    return {"files": files, "count": len(files)}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), principal: Principal = Depends(get_current_principal)):
    """Upload file untuk diproses agent (PDF, image, txt, kml)."""
    safe_name = os.path.basename(file.filename or "")
    ext = os.path.splitext(safe_name)[1].lower()
    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".csv", ".md", ".kml", ".json"}
    if not safe_name or ext not in allowed:
        raise HTTPException(status_code=400, detail=f"File type {ext} not allowed")

    path = os.path.join(UPLOADS_DIR, safe_name)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {
        "filename": safe_name,
        "path": path,
        "size": os.path.getsize(path),
        "ext": ext,
    }


@router.get("/uploads")
async def list_uploads(principal: Principal = Depends(get_current_principal)):
    """List file yang sudah diupload."""
    files = []
    for f in sorted(os.listdir(UPLOADS_DIR)):
        path = os.path.join(UPLOADS_DIR, f)
        files.append({"filename": f, "path": path, "size": os.path.getsize(path)})
    return {"files": files}
