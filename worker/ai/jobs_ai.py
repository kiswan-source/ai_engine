"""AI background jobs via RQ."""
import asyncio
import time
from datetime import datetime

import redis
from rq import Queue, get_current_job

from api.config import settings
from core.utils.logger import get_logger

logger = get_logger(__name__)

_redis_conn = redis.from_url(settings.REDIS_URL)
ai_queue = Queue(settings.RQ_QUEUE_AI, connection=_redis_conn)


def run_ai_job(prompt: str, system: str = "", model: str = "") -> dict:
    """
    Synchronous RQ job — runs Gemma generation in a worker process.
    RQ workers are sync; we run async code via asyncio.run().
    """
    import asyncio
    from core.ai.gemma_client import GemmaClient

    job = get_current_job()
    logger.info("AI job started", job_id=job.id if job else "direct")

    start = time.time()
    try:
        async def _run():
            async with GemmaClient() as client:
                return await client.generate(prompt=prompt, system=system)

        result = asyncio.run(_run())
        duration_ms = int((time.time() - start) * 1000)

        logger.info("AI job completed", duration_ms=duration_ms)
        return {
            "status": "completed",
            "result": result,
            "duration_ms": duration_ms,
            "completed_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error("AI job failed", error=str(e))
        raise


async def enqueue_ai_job(
    prompt: str,
    system: str = "",
    priority: str = "normal",
) -> str:
    """Enqueue an AI job and return the job ID."""
    timeout_map = {"low": 300, "normal": 120, "high": 60}
    job = ai_queue.enqueue(
        run_ai_job,
        kwargs={"prompt": prompt, "system": system},
        job_timeout=timeout_map.get(priority, 120),
        result_ttl=86400,
    )
    logger.info("AI job enqueued", job_id=job.id, priority=priority)
    return job.id
