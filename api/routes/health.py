"""Health check endpoints."""
import redis.asyncio as aioredis
from fastapi import APIRouter
from api.config import settings
from core.ai.gemma_client import gemma
from db.connection import get_db_status

router = APIRouter()


@router.get("/")
async def health():
    return {"status": "ok", "service": settings.APP_NAME}


@router.get("/ready")
async def readiness():
    """Full readiness check — DB, Redis, Ollama."""
    checks = {}

    # Database
    checks["database"] = await get_db_status()

    # Redis
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # Ollama / Gemma
    checks["ollama"] = await gemma.health_check()

    all_ok = (
        checks["database"] == "ok"
        and checks["redis"] == "ok"
        and checks["ollama"].get("ollama") == "ok"
    )

    return {
        "ready": all_ok,
        "checks": checks,
    }
