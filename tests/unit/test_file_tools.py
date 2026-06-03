"""Unit tests for the new GIS I/O and image transform tools."""
import os
import json
import zipfile

import pytest

from agent.tools import gis_io, images

SAMPLE_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>Blok A</name><Polygon><outerBoundaryIs><LinearRing>
<coordinates>110.0,-7.0,0 110.1,-7.0,0 110.1,-7.1,0 110.0,-7.1,0 110.0,-7.0,0</coordinates>
</LinearRing></outerBoundaryIs></Polygon></Placemark>
</Document></kml>"""


@pytest.fixture
def kml_file(tmp_path):
    p = tmp_path / "blok.kml"
    p.write_text(SAMPLE_KML, encoding="utf-8")
    return str(p)


@pytest.fixture
def png_file(tmp_path):
    from PIL import Image
    p = tmp_path / "pic.png"
    Image.new("RGBA", (200, 100), (255, 0, 0, 255)).save(str(p))
    return str(p)


# ─── GIS ───────────────────────────────────────────────────────────────────────
def test_kml_to_geojson(kml_file):
    res = gis_io.convert_geo(kml_file, "geojson")
    assert res["success"] and res["type"] == "geojson"
    assert os.path.exists(res["file"])
    data = json.loads(open(res["file"]).read())
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 1


def test_kml_to_shp_and_back(kml_file):
    shp = gis_io.convert_geo(kml_file, "shp")
    assert shp["success"] and shp["file"].endswith(".zip")
    with zipfile.ZipFile(shp["file"]) as z:
        exts = {os.path.splitext(n)[1].lower() for n in z.namelist()}
    assert {".shp", ".shx", ".dbf"}.issubset(exts)
    # round-trip: read the zip back
    summary = gis_io.read_shp(shp["file"])
    assert summary["feature_count"] == 1
    assert summary["total_area_ha"] > 0


def test_write_read_geojson(tmp_path):
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "X"},
         "geometry": {"type": "Polygon", "coordinates": [
             [[110, -7], [110.1, -7], [110.1, -7.1], [110, -7]]]}}]}
    res = gis_io.write_geojson("test_out.geojson", fc)
    assert res["success"]
    read = gis_io.read_geojson(res["file"])
    assert read["feature_count"] == 1


# ─── Images ─────────────────────────────────────────────────────────────────────
def test_image_convert_png_to_jpg(png_file):
    res = images.image_convert(png_file, "jpg")
    assert res["success"] and res["file"].endswith(".jpg")
    assert os.path.exists(res["file"])


def test_image_resize_keeps_aspect(png_file):
    res = images.image_resize(png_file, width=100)
    assert res["success"]
    assert res["width"] == 100 and res["height"] == 50  # 200x100 -> 100x50


def test_image_to_tiff(png_file):
    res = images.image_convert(png_file, "tiff")
    assert res["success"] and res["file"].lower().endswith(".tiff")


def test_images_to_pdf(png_file):
    res = images.images_to_pdf([png_file], "combined.pdf")
    assert res["success"] and res["page_count"] == 1
    assert os.path.exists(res["file"])
