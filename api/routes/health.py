"""Health check endpoints."""
from fastapi import APIRouter
from api.config import settings
from telemetry.monitoring import check_readiness

router = APIRouter()


@router.get("/")
async def health():
    return {"status": "ok", "service": settings.APP_NAME}


@router.get("/ready")
async def readiness():
    """Full readiness check — DB, Redis, Ollama, and every enabled cloud
    provider (Bab 35 rule 3). Shared with telemetry.monitoring.health_dashboard()
    so the route and the dashboard can't drift into different answers."""
    return await check_readiness()
