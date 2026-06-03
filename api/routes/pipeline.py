"""
Pipeline endpoints — orchestrate multi-step AI + GIS workflows.
Example: Upload KML → Spatial analysis → AI report → Store to DB.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.gis.processor import KMLProcessor, haversine_area_ha, centroid, bbox
from core.ai.gemma_client import gemma
from core.ai.prompt_templates import (
    PromptTemplate, render, GEMMA_SYSTEM_MINING,
)
from worker.pipeline.jobs_pipeline import enqueue_pipeline_job
from core.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/wiup-full-report")
async def wiup_full_pipeline(
    location: str,
    commodity: str = "Batu Andesit",
    file: UploadFile = File(...),
):
    """
    Full WIUP pipeline:
    1. Parse KML polygon
    2. Compute spatial statistics
    3. AI geological analysis
    4. AI permit narrative
    5. Return complete report
    """
    # Step 1: Parse KML
    content = (await file.read()).decode("utf-8")
    polygons = KMLProcessor.parse(content)
    if not polygons:
        raise HTTPException(status_code=422, detail="No polygons found in KML")

    poly = polygons[0]  # use first polygon

    # Step 2: Spatial stats
    coords = poly["coordinates"]
    area_ha = poly["area_ha"]
    ctr = poly["centroid"]
    bb = poly["bbox"]

    # Step 3: AI geological analysis
    geo_prompt = render(
        PromptTemplate.GEOLOGICAL_SUMMARY,
        data=f"Lokasi: {location}, Komoditas: {commodity}, Luas: {area_ha} Ha, "
             f"Koordinat centroid: {ctr['latitude']}°LS {ctr['longitude']}°BT",
    )
    geological_summary = await gemma.generate(
        prompt=geo_prompt, system=GEMMA_SYSTEM_MINING, temperature=0.4
    )

    # Step 4: AI permit narrative
    wiup_prompt = render(
        PromptTemplate.WIUP_AREA_ANALYSIS,
        coordinates=f"{coords[:3]}…",
        area_ha=area_ha,
        location=location,
    )
    permit_narrative = await gemma.generate(
        prompt=wiup_prompt, system=GEMMA_SYSTEM_MINING, temperature=0.3
    )

    return {
        "pipeline": "wiup_full_report",
        "status": "completed",
        "input": {
            "location": location,
            "commodity": commodity,
            "polygon_name": poly["name"],
        },
        "spatial": {
            "area_ha": area_ha,
            "centroid": ctr,
            "bbox": bb,
            "vertex_count": poly["vertex_count"],
        },
        "ai_reports": {
            "geological_summary": geological_summary,
            "permit_narrative": permit_narrative,
        },
    }


class AsyncPipelineRequest(BaseModel):
    pipeline_type: str  # wiup_report | geological_analysis | document_review
    params: dict
    priority: str = "normal"


@router.post("/async/enqueue")
async def enqueue_async_pipeline(req: AsyncPipelineRequest):
    """Enqueue a long-running pipeline job via RQ."""
    job_id = await enqueue_pipeline_job(
        pipeline_type=req.pipeline_type,
        params=req.params,
        priority=req.priority,
    )
    return {"job_id": job_id, "status": "queued", "pipeline": req.pipeline_type}
