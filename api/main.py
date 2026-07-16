"""
AI Engine — FastAPI Application Entry Point
Integrates Gemma 4:26B via Ollama with GIS + document processing pipelines.
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from api.config import settings
from api.middleware import setup_middleware
from security.auth import get_current_principal
from security.startup_validation import enforce_production_config
from api.routes import health, ai, gis, pipeline, docs as docs_router
from core.utils.logger import get_logger
from db.connection import init_db, close_db
from api.routes import agent as agent_router
from api.routes import dokumen as dokumen_router
from api.routes import files as files_router
from api.routes import chat as chat_router
from api.routes import orchestrator as orchestrator_router
from api.routes import monitoring as monitoring_router
from api.routes import memory as memory_router
from api.routes import knowledge as knowledge_router
from api.routes import projects as projects_router
from api.routes import automation as automation_router
from api.routes import plugins as plugins_router
from api.routes import workspace as workspace_router
from improvement.scheduler import ImprovementScheduler

logger = get_logger(__name__)

# Fase 7 (DCF v5 mandate, Continuous Improvement Engine) — module-level
# singleton, same pattern as automation_router._scheduler above. Always
# started: analysis is read-only/safe (same "telemetry has no on/off
# switch" reasoning CLAUDE.md §10 already applies) — only the separate
# ENABLE_AUTONOMOUS_IMPROVEMENT flag (default off) gates whether a tick
# ever actually writes a config change.
_improvement_scheduler = ImprovementScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & shutdown lifecycle."""
    logger.info("🚀 AI Engine starting up…", env=settings.APP_ENV)
    # Fase 0 / SEC-1, SEC-2 (fail-closed): refuses to start in production with
    # blank/example/weak credentials, instead of silently granting full access.
    # No-op outside APP_ENV=production, so local/dev workflows are unaffected.
    enforce_production_config(settings)
    await init_db()
    logger.info("✅ Database connected")
    if settings.ENABLE_SCHEDULER:
        await automation_router._scheduler.start()
    await _improvement_scheduler.start()
    yield
    logger.info("🛑 AI Engine shutting down…")
    if settings.ENABLE_SCHEDULER:
        await automation_router._scheduler.stop()
    await _improvement_scheduler.stop()
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
# web/ is now the React app's source (FRONTEND_ARCHITECTURE.md §1) — built via
# `npm run build` (web/) into web/dist/, which is what's served in production.
# In dev, run `npm run dev` in web/ separately (Vite dev server, proxying
# /api and /health back to this app per web/vite.config.ts) instead of hitting
# this app's "/" directly.
WEB_DIST_DIR = BASE_DIR / "web" / "dist"
if (WEB_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIST_DIR / "assets")), name="web-assets")

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
# Fase 1 / SEC-1 follow-up: these 5 routers had no auth dependency at all
# (found while wiring the Fase-0 fail-closed startup guard — every other
# router already opts into get_current_principal per-route). Applied at
# router level, not per-endpoint, so a future endpoint added to any of these
# can't ship unauthenticated by omission. No-op today: API_KEYS is blank
# (Fase 0 chose loopback-only network isolation over API-key auth), so
# get_current_principal still returns an admin Principal for every caller.
_AUTH = [Depends(get_current_principal)]
app.include_router(ai.router, prefix="/api/v1/ai", tags=["AI"], dependencies=_AUTH)
# Domain Skills (Fase 5, DCF v5 mandate "Domain Generalization") — gis/dokumen/
# pipeline are 100% mining/GIS content (pipeline.py's only sync route is
# wiup-full-report), not core-engine routes; gated as one unit so the
# platform can run without this domain skill at all — see
# agent/tools/registry.py's matching gate and tests/unit/test_domain_skill_toggle.py.
if settings.ENABLE_MINING_GIS_SKILL:
    app.include_router(gis.router, prefix="/api/v1/gis", tags=["GIS"], dependencies=_AUTH)
    app.include_router(pipeline.router, prefix="/api/v1/pipeline", tags=["Pipeline"], dependencies=_AUTH)
    app.include_router(dokumen_router.router, prefix="/api/dokumen", tags=["Dokumen"], dependencies=_AUTH)
app.include_router(docs_router.router, prefix="/api/v1/docs", tags=["Documents"], dependencies=_AUTH)
app.include_router(agent_router.router, prefix="/api/v1/agent", tags=["Agent"])
app.include_router(files_router.router, prefix="", tags=["Files"])
app.include_router(chat_router.router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(orchestrator_router.router, prefix="/api/v1/orchestrator", tags=["Orchestrator"])
app.include_router(monitoring_router.router, prefix="/api/v1/monitoring", tags=["Monitoring"])
app.include_router(memory_router.router, prefix="/api/v1/memory", tags=["Memory"])
app.include_router(knowledge_router.router, prefix="/api/v1/knowledge", tags=["Knowledge"])
app.include_router(projects_router.router, prefix="/api/v1/projects", tags=["Projects"])
app.include_router(automation_router.router, prefix="/api/v1/automation", tags=["Automation"])
app.include_router(plugins_router.router, prefix="/api/v1/plugins", tags=["Plugins"])
app.include_router(workspace_router.router, prefix="/api/v1/workspace", tags=["Workspace"])

if (WEB_DIST_DIR / "index.html").exists():
    # SPA fallback: React Router (FRONTEND_ARCHITECTURE.md §5) owns client-side
    # routes like /chat, /workflow, /approval — a hard refresh/direct link on
    # any of those must still get index.html from the server, not a 404.
    # Registered last so it never shadows the API routers/mount above it.
    @app.get("/{full_path:path}", tags=["Root"], include_in_schema=False)
    async def serve_spa(full_path: str):
        candidate = WEB_DIST_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB_DIST_DIR / "index.html")
else:

    @app.get("/", tags=["Root"], include_in_schema=False)
    async def root():
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
