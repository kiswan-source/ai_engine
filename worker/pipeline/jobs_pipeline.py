"""Pipeline background jobs — multi-step workflows."""
import asyncio
import redis
from rq import Queue, get_current_job

from api.config import settings
from core.utils.logger import get_logger

logger = get_logger(__name__)
_redis_conn = redis.from_url(settings.REDIS_URL)
pipeline_queue = Queue(settings.RQ_QUEUE_PIPELINE, connection=_redis_conn)


def run_pipeline_job(pipeline_type: str, params: dict) -> dict:
    """Dispatcher for async pipeline jobs."""
    job = get_current_job()
    logger.info("Pipeline job started", type=pipeline_type, job_id=job.id if job else "direct")

    if pipeline_type == "wiup_report":
        return asyncio.run(_run_wiup_report(params))
    elif pipeline_type == "document_review":
        return asyncio.run(_run_document_review(params))
    else:
        raise ValueError(f"Unknown pipeline: {pipeline_type}")


async def _run_wiup_report(params: dict) -> dict:
    from core.ai.gemma_client import GemmaClient
    from core.gis.processor import haversine_area_ha, centroid
    from core.ai.prompt_templates import PromptTemplate, render, GEMMA_SYSTEM_MINING

    coords = params.get("coordinates", [])
    location = params.get("location", "Unknown")
    commodity = params.get("commodity", "Mineral")

    area_ha = haversine_area_ha(coords) if coords else 0
    ctr = centroid(coords) if coords else {}

    async with GemmaClient() as client:
        summary = await client.generate(
            prompt=render(PromptTemplate.GEOLOGICAL_SUMMARY,
                         data=f"Lokasi: {location}, Komoditas: {commodity}, Luas: {area_ha} Ha"),
            system=GEMMA_SYSTEM_MINING,
            temperature=0.4,
        )

    return {
        "pipeline": "wiup_report",
        "location": location,
        "area_ha": area_ha,
        "geological_summary": summary,
    }


async def _run_document_review(params: dict) -> dict:
    from core.ai.gemma_client import GemmaClient
    from core.ai.prompt_templates import PromptTemplate, render

    text = params.get("text", "")
    async with GemmaClient() as client:
        summary = await client.generate(
            prompt=render(PromptTemplate.DOCUMENT_SUMMARIZE, text=text, max_words=300),
            temperature=0.3,
        )
        entities = await client.generate_json(
            prompt=render(PromptTemplate.DOCUMENT_EXTRACT_ENTITIES, text=text[:3000]),
        )
    return {"pipeline": "document_review", "summary": summary, "entities": entities}


async def enqueue_pipeline_job(pipeline_type: str, params: dict, priority: str = "normal") -> str:
    job = pipeline_queue.enqueue(
        run_pipeline_job,
        kwargs={"pipeline_type": pipeline_type, "params": params},
        job_timeout=600,
        result_ttl=86400,
    )
    return job.id
