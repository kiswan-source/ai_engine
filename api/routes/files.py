"""File serving & upload endpoints untuk Agent."""
import os
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()
REPORTS_DIR = os.path.expanduser("~/ai_engine/reports")
UPLOADS_DIR = os.path.expanduser("~/ai_engine/uploads")
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)


@router.get("/reports/{filename}")
async def download_report(filename: str):
    """Download file hasil agent."""
    path = os.path.join(REPORTS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=filename)


@router.get("/reports")
async def list_reports():
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
async def upload_file(file: UploadFile = File(...)):
    """Upload file untuk diproses agent (PDF, image, txt, kml)."""
    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".csv", ".md", ".kml", ".json"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"File type {ext} not allowed")

    path = os.path.join(UPLOADS_DIR, file.filename)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {
        "filename": file.filename,
        "path": path,
        "size": os.path.getsize(path),
        "ext": ext,
    }


@router.get("/uploads")
async def list_uploads():
    """List file yang sudah diupload."""
    files = []
    for f in sorted(os.listdir(UPLOADS_DIR)):
        path = os.path.join(UPLOADS_DIR, f)
        files.append({"filename": f, "path": path, "size": os.path.getsize(path)})
    return {"files": files}
