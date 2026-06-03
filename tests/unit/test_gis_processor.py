"""
Unit Tests — GIS Processor
Run: pytest tests/unit/test_gis_processor.py -v
"""
import pytest
import math
from core.gis.processor import (
    haversine_area_ha,
    centroid,
    bbox,
    KMLProcessor,
    GeoJSONProcessor,
)

# ─── Sample data ──────────────────────────────────────────────────────────────
# Approximate square ~1km × 1km near Ciwandan, Cilegon
SAMPLE_COORDS = [
    [106.0000, -6.0000],
    [106.0090, -6.0000],
    [106.0090, -6.0090],
    [106.0000, -6.0090],
    [106.0000, -6.0000],
]

SAMPLE_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Placemark>
    <name>Test Polygon</name>
    <Polygon>
      <outerBoundaryIs>
        <LinearRing>
          <coordinates>
            106.0000,-6.0000,0
            106.0090,-6.0000,0
            106.0090,-6.0090,0
            106.0000,-6.0090,0
            106.0000,-6.0000,0
          </coordinates>
        </LinearRing>
      </outerBoundaryIs>
    </Polygon>
  </Placemark>
</kml>"""


# ─── Area Tests ───────────────────────────────────────────────────────────────
class TestHaversineArea:
    def test_square_returns_positive_area(self):
        area = haversine_area_ha(SAMPLE_COORDS)
        assert area > 0

    def test_square_approx_100ha(self):
        """~0.009° × ~0.009° at equator ≈ 90–100 Ha."""
        area = haversine_area_ha(SAMPLE_COORDS)
        assert 85 < area < 115, f"Expected ~100 Ha, got {area}"

    def test_open_ring_auto_closed(self):
        """Open ring (no repeated first point) should still work."""
        open_ring = SAMPLE_COORDS[:-1]
        area = haversine_area_ha(open_ring)
        assert area > 0

    def test_empty_returns_zero(self):
        assert haversine_area_ha([]) == 0.0

    def test_triangle_smaller_than_square(self):
        triangle = [
            [106.0000, -6.0000],
            [106.0090, -6.0000],
            [106.0045, -6.0090],
        ]
        tri_area = haversine_area_ha(triangle)
        sq_area = haversine_area_ha(SAMPLE_COORDS)
        assert tri_area < sq_area

    def test_result_is_rounded_to_4dp(self):
        area = haversine_area_ha(SAMPLE_COORDS)
        assert area == round(area, 4)


# ─── Centroid Tests ───────────────────────────────────────────────────────────
class TestCentroid:
    def test_centroid_of_square(self):
        ctr = centroid(SAMPLE_COORDS)
        assert abs(ctr["longitude"] - 106.0045) < 0.001
        assert abs(ctr["latitude"] - (-6.0045)) < 0.001

    def test_centroid_returns_dict_with_keys(self):
        ctr = centroid(SAMPLE_COORDS)
        assert "longitude" in ctr and "latitude" in ctr


# ─── BBox Tests ───────────────────────────────────────────────────────────────
class TestBBox:
    def test_bbox_keys(self):
        bb = bbox(SAMPLE_COORDS)
        assert all(k in bb for k in ["min_lon", "max_lon", "min_lat", "max_lat"])

    def test_bbox_values(self):
        bb = bbox(SAMPLE_COORDS)
        assert bb["min_lon"] == 106.0
        assert bb["max_lon"] == 106.009
        assert bb["min_lat"] == -6.009
        assert bb["max_lat"] == -6.0


# ─── KML Parser Tests ─────────────────────────────────────────────────────────
class TestKMLProcessor:
    def test_parse_returns_polygons(self):
        result = KMLProcessor.parse(SAMPLE_KML)
        assert len(result) == 1

    def test_parse_polygon_has_name(self):
        result = KMLProcessor.parse(SAMPLE_KML)
        assert result[0]["name"] == "Test Polygon"

    def test_parse_polygon_has_area(self):
        result = KMLProcessor.parse(SAMPLE_KML)
        assert result[0]["area_ha"] > 0

    def test_parse_polygon_has_centroid(self):
        result = KMLProcessor.parse(SAMPLE_KML)
        assert "centroid" in result[0]
        assert "longitude" in result[0]["centroid"]

    def test_parse_empty_kml_returns_empty(self):
        empty_kml = """<?xml version="1.0"?>
        <kml xmlns="http://www.opengis.net/kml/2.2"><Document></Document></kml>"""
        result = KMLProcessor.parse(empty_kml)
        assert result == []

    def test_to_geojson_feature_collection(self):
        geojson = KMLProcessor.to_geojson(SAMPLE_KML)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1
        assert geojson["features"][0]["geometry"]["type"] == "Polygon"


# ─── GeoJSON Validator Tests ──────────────────────────────────────────────────
class TestGeoJSONProcessor:
    def test_valid_polygon(self):
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [SAMPLE_COORDS],
                    },
                    "properties": {},
                }
            ],
        }
        result = GeoJSONProcessor.validate(geojson)
        assert result["valid"] is True
        assert result["errors"] == []

    def test_invalid_type(self):
        result = GeoJSONProcessor.validate({"type": "InvalidType"})
        assert result["valid"] is False

    def test_enrich_adds_area(self):
        geojson = KMLProcessor.to_geojson(SAMPLE_KML)
        enriched = GeoJSONProcessor.enrich(geojson)
        props = enriched["features"][0]["properties"]
        assert "area_ha" in props
        assert props["area_ha"] > 0
