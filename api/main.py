"""
AI Engine — FastAPI Application Entry Point
Integrates Gemma 4:26B via Ollama with GIS + document processing pipelines.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from api.config import settings
from api.middleware import setup_middleware
from api.routes import health, ai, gis, pipeline, docs as docs_router
from core.utils.logger import get_logger
from db.connection import init_db, close_db
from api.routes import agent as agent_router
from api.routes import dokumen as dokumen_router
from api.routes import files as files_router
from api.routes import chat as chat_router
from api.routes import orchestrator as orchestrator_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & shutdown lifecycle."""
    logger.info("🚀 AI Engine starting up…", env=settings.APP_ENV)
    await init_db()
    logger.info("✅ Database connected")
    yield
    logger.info("🛑 AI Engine shutting down…")
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Production AI Engine — Gemma 4:26B · FastAPI · PostGIS · RQ",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
setup_middleware(app)

# Serve UI
from fastapi.responses import FileResponse

BASE_DIR = Path(__file__).parent.parent
WEB_DIR = BASE_DIR / "web"
if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")

ui_path = BASE_DIR / "ai_engine_ui.html"
if ui_path.exists():
    @app.get("/ui")
    async def serve_ui():
        return FileResponse(ui_path)

v3_path = BASE_DIR / "ai_engine_ui_v3.html"
if v3_path.exists():
    @app.get("/v3")
    async def serve_v3():
        return FileResponse(v3_path)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["AI"])
app.include_router(gis.router, prefix="/api/v1/gis", tags=["GIS"])
app.include_router(pipeline.router, prefix="/api/v1/pipeline", tags=["Pipeline"])
app.include_router(docs_router.router, prefix="/api/v1/docs", tags=["Documents"])
app.include_router(agent_router.router, prefix="/api/v1/agent", tags=["Agent"])
app.include_router(files_router.router, prefix="", tags=["Files"])
app.include_router(dokumen_router.router, prefix="/api/dokumen", tags=["Dokumen"])
app.include_router(chat_router.router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(orchestrator_router.router, prefix="/api/v1/orchestrator", tags=["Orchestrator"])

@app.get("/", tags=["Root"], include_in_schema=False)
async def root():
    index = WEB_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {
        "app": settings.APP_NAME,
        "version": "1.0.0",
        "status": "ok",
        "links": {"docs": "/docs", "chat": "/", "legacy_ui": "/ui"},
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled exception", error=str(exc), path=str(request.url))
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

# ── CORS fix + static file serving ──────────────────────────
