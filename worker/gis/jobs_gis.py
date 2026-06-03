"""GIS background jobs via RQ."""
import redis
from rq import Queue, get_current_job

from api.config import settings
from core.gis.processor import KMLProcessor, GeoJSONProcessor
from core.utils.logger import get_logger

logger = get_logger(__name__)

_redis_conn = redis.from_url(settings.REDIS_URL)
gis_queue = Queue(settings.RQ_QUEUE_GIS, connection=_redis_conn)


def run_kml_processing_job(kml_content: str, location: str = "") -> dict:
    """Parse KML, compute spatial stats, enrich with metadata."""
    job = get_current_job()
    logger.info("GIS job started", job_id=job.id if job else "direct", location=location)

    polygons = KMLProcessor.parse(kml_content)
    geojson = KMLProcessor.to_geojson(kml_content)
    enriched = GeoJSONProcessor.enrich(geojson)

    total_area = sum(p["area_ha"] for p in polygons)

    return {
        "status": "completed",
        "polygon_count": len(polygons),
        "total_area_ha": total_area,
        "polygons": polygons,
        "geojson": enriched,
    }


async def enqueue_gis_job(kml_content: str, location: str = "") -> str:
    job = gis_queue.enqueue(
        run_kml_processing_job,
        kwargs={"kml_content": kml_content, "location": location},
        job_timeout=300,
        result_ttl=86400,
    )
    return job.id
