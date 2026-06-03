"""GIS endpoints — KML processing, area calculation, WIUP analysis."""
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.gis.processor import KMLProcessor, GeoJSONProcessor, haversine_area_ha
from core.ai.gemma_client import gemma
from core.ai.prompt_templates import (
    PromptTemplate, render, GEMMA_SYSTEM_MINING, GEMMA_SYSTEM_GIS,
)
from core.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


class WIUPAnalysisRequest(BaseModel):
    coordinates: list[list[float]]
    location: str
    commodity: Optional[str] = "Batu Andesit"


@router.post("/kml/parse")
async def parse_kml(file: UploadFile = File(...)):
    """Parse uploaded KML file and return polygon metadata."""
    if not file.filename.endswith(".kml"):
        raise HTTPException(status_code=400, detail="File must be .kml")

    content = (await file.read()).decode("utf-8")
    polygons = KMLProcessor.parse(content)

    if not polygons:
        raise HTTPException(status_code=422, detail="No polygons found in KML")

    return {"count": len(polygons), "polygons": polygons}


@router.post("/kml/to-geojson")
async def kml_to_geojson(file: UploadFile = File(...)):
    """Convert KML to GeoJSON FeatureCollection."""
    content = (await file.read()).decode("utf-8")
    return KMLProcessor.to_geojson(content)


@router.post("/area/calculate")
async def calculate_area(coordinates: list[list[float]]):
    """Calculate polygon area in hectares (WGS-84 spherical)."""
    if len(coordinates) < 3:
        raise HTTPException(status_code=400, detail="Need at least 3 coordinate pairs")

    from core.gis.processor import centroid, bbox
    return {
        "area_ha": haversine_area_ha(coordinates),
        "centroid": centroid(coordinates),
        "bbox": bbox(coordinates),
        "vertex_count": len(coordinates),
    }


@router.post("/wiup/analyze")
async def wiup_analyze(req: WIUPAnalysisRequest):
    """
    Full WIUP area analysis — spatial stats + AI narrative for Minerba permit.
    """
    area_ha = haversine_area_ha(req.coordinates)
    from core.gis.processor import centroid, bbox
    ctr = centroid(req.coordinates)
    bb = bbox(req.coordinates)

    prompt = render(
        PromptTemplate.WIUP_AREA_ANALYSIS,
        coordinates=str(req.coordinates[:5]) + "…",
        area_ha=area_ha,
        location=req.location,
    )

    ai_analysis = await gemma.generate(
        prompt=prompt,
        system=GEMMA_SYSTEM_MINING,
        temperature=0.4,
    )

    return {
        "location": req.location,
        "commodity": req.commodity,
        "spatial": {
            "area_ha": area_ha,
            "centroid": ctr,
            "bbox": bb,
            "vertex_count": len(req.coordinates),
        },
        "ai_analysis": ai_analysis,
    }


@router.post("/geojson/validate")
async def validate_geojson(geojson: dict):
    """Validate GeoJSON structure and compute spatial properties."""
    validation = GeoJSONProcessor.validate(geojson)
    if validation["valid"]:
        enriched = GeoJSONProcessor.enrich(geojson)
        return {"valid": True, "geojson": enriched}
    return {"valid": False, "errors": validation["errors"]}
