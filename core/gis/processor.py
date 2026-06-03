"""
GIS Processor — KML/GeoJSON/Shapefile processing with PostGIS spatial queries.
Built for Indonesian mining permit (WIUP/IUP) workflows.
"""
import json
import math
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from core.utils.logger import get_logger

logger = get_logger(__name__)

WGS84_EARTH_RADIUS_M = 6_378_137.0


def haversine_area_ha(coordinates: list[list[float]]) -> float:
    """
    Compute polygon area in hectares using the spherical excess formula (WGS-84).
    coordinates: list of [lon, lat] pairs (ring closed or open).
    """
    if len(coordinates) < 3:
        return 0.0

    ring = coordinates[:]
    if ring[0] != ring[-1]:
        ring.append(ring[0])

    n = len(ring) - 1
    total = 0.0
    for i in range(n):
        lon1, lat1 = math.radians(ring[i][0]), math.radians(ring[i][1])
        lon2, lat2 = math.radians(ring[i + 1][0]), math.radians(ring[i + 1][1])
        total += (lon2 - lon1) * (2 + math.sin(lat1) + math.sin(lat2))

    area_m2 = abs(total * WGS84_EARTH_RADIUS_M**2 / 2)
    return round(area_m2 / 10_000, 4)


def centroid(coordinates: list[list[float]]) -> dict:
    """Return centroid [lon, lat] of polygon ring."""
    lons = [c[0] for c in coordinates]
    lats = [c[1] for c in coordinates]
    return {
        "longitude": round(sum(lons) / len(lons), 6),
        "latitude": round(sum(lats) / len(lats), 6),
    }


def bbox(coordinates: list[list[float]]) -> dict:
    """Return bounding box of polygon."""
    lons = [c[0] for c in coordinates]
    lats = [c[1] for c in coordinates]
    return {
        "min_lon": round(min(lons), 6),
        "max_lon": round(max(lons), 6),
        "min_lat": round(min(lats), 6),
        "max_lat": round(max(lats), 6),
    }


class KMLProcessor:
    """Parse and analyse KML polygon files."""

    NAMESPACES = {
        "kml": "http://www.opengis.net/kml/2.2",
        "": "http://www.opengis.net/kml/2.2",
    }

    @classmethod
    def parse(cls, kml_content: str) -> list[dict]:
        """Extract all polygons from KML string. Returns list of polygon dicts."""
        root = ET.fromstring(kml_content)
        ns = "http://www.opengis.net/kml/2.2"
        polygons = []

        for placemark in root.iter(f"{{{ns}}}Placemark"):
            name_el = placemark.find(f"{{{ns}}}name")
            name = name_el.text if name_el is not None else "Unnamed"

            for poly in placemark.iter(f"{{{ns}}}Polygon"):
                outer = poly.find(
                    f"{{{ns}}}outerBoundaryIs/{{{ns}}}LinearRing/{{{ns}}}coordinates"
                )
                if outer is None or not outer.text:
                    continue

                coords = cls._parse_coords(outer.text)
                if not coords:
                    continue

                area = haversine_area_ha(coords)
                polygons.append(
                    {
                        "name": name,
                        "coordinates": coords,
                        "area_ha": area,
                        "centroid": centroid(coords),
                        "bbox": bbox(coords),
                        "vertex_count": len(coords),
                    }
                )

        logger.info("KML parsed", polygons=len(polygons))
        return polygons

    @staticmethod
    def _parse_coords(raw: str) -> list[list[float]]:
        """Parse KML coordinate string to [[lon, lat], …]."""
        coords = []
        for token in raw.strip().split():
            parts = token.split(",")
            if len(parts) >= 2:
                try:
                    lon, lat = float(parts[0]), float(parts[1])
                    # Keep ~1mm precision (8 dp). Rounding to 4 dp snapped points
                    # to an ~11m grid, which inflated areas and collapsed thin
                    # cadastral slivers to 0.0 Ha — wrong for "presisi" data.
                    coords.append([round(lon, 8), round(lat, 8)])
                except ValueError:
                    continue
        return coords

    @classmethod
    def to_geojson(cls, kml_content: str) -> dict:
        """Convert KML polygons to GeoJSON FeatureCollection."""
        polygons = cls.parse(kml_content)
        features = []
        for p in polygons:
            ring = p["coordinates"]
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "properties": {
                        "name": p["name"],
                        "area_ha": p["area_ha"],
                        "centroid_lon": p["centroid"]["longitude"],
                        "centroid_lat": p["centroid"]["latitude"],
                    },
                }
            )
        return {"type": "FeatureCollection", "features": features}


class GeoJSONProcessor:
    """Validate and enrich GeoJSON polygon data."""

    @staticmethod
    def validate(geojson: dict) -> dict:
        """Basic GeoJSON validation. Returns {valid, errors}."""
        errors = []
        if geojson.get("type") not in ("FeatureCollection", "Feature", "Polygon"):
            errors.append("Invalid GeoJSON type")

        features = (
            geojson.get("features", [])
            if geojson.get("type") == "FeatureCollection"
            else [geojson]
        )
        for i, f in enumerate(features):
            geom = f.get("geometry", {})
            if geom.get("type") != "Polygon":
                errors.append(f"Feature {i}: expected Polygon geometry")
            coords = geom.get("coordinates", [[]])
            if len(coords[0]) < 4:
                errors.append(f"Feature {i}: polygon needs at least 4 coordinate pairs")

        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def enrich(geojson: dict) -> dict:
        """Add computed properties (area, centroid, bbox) to each feature."""
        features = geojson.get("features", [])
        for f in features:
            coords = f.get("geometry", {}).get("coordinates", [[]])[0]
            if coords:
                f["properties"]["area_ha"] = haversine_area_ha(coords)
                f["properties"]["centroid"] = centroid(coords)
                f["properties"]["bbox"] = bbox(coords)
        return geojson
