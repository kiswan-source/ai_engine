"""
GIS I/O tools — read/write/convert GeoJSON, KML, and Shapefile (SHP).

Everything funnels through an in-memory GeoJSON FeatureCollection as the common
format. Reuses core/gis/processor.py for KML parsing + area/centroid/bbox so we
never duplicate the spatial math.
"""
import os
import json
import shutil
import zipfile
import tempfile
from collections import Counter
from typing import Any, Dict, List

from core.gis.processor import (
    KMLProcessor,
    haversine_area_ha,
    centroid as _centroid,
    bbox as _bbox,
)
from core.utils.logger import get_logger

logger = get_logger(__name__)

OUTPUT_DIR = os.path.expanduser("~/ai_engine/reports")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _out_path(filename: str) -> str:
    return filename if os.path.dirname(filename) else os.path.join(OUTPUT_DIR, filename)


def _rings_of(geom: dict) -> List[List[List[float]]]:
    """Return list of outer rings ([[lon,lat],...]) for Polygon/MultiPolygon."""
    if not geom:
        return []
    t = geom.get("type")
    coords = geom.get("coordinates", [])
    if t == "Polygon":
        return [coords[0]] if coords else []
    if t == "MultiPolygon":
        return [poly[0] for poly in coords if poly]
    return []


# ─── Load any supported file → GeoJSON FeatureCollection ────────────────────────
def _load_geojson_fc(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("type") == "FeatureCollection":
        return data
    if data.get("type") == "Feature":
        return {"type": "FeatureCollection", "features": [data]}
    if data.get("type") in ("Polygon", "MultiPolygon", "Point", "LineString"):
        return {"type": "FeatureCollection",
                "features": [{"type": "Feature", "geometry": data, "properties": {}}]}
    raise ValueError("Unrecognised GeoJSON structure")


def _load_kml_fc(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return KMLProcessor.to_geojson(f.read())


def _load_shp_fc(path: str) -> Dict[str, Any]:
    """Read a .shp (with sibling .dbf/.shx) or a .zip bundle → FeatureCollection."""
    import fiona

    tmpdir = None
    shp_path = path
    if path.lower().endswith(".zip"):
        tmpdir = tempfile.mkdtemp(prefix="shp_")
        with zipfile.ZipFile(path) as z:
            z.extractall(tmpdir)
        shp_files = [os.path.join(r, fn) for r, _, fs in os.walk(tmpdir)
                     for fn in fs if fn.lower().endswith(".shp")]
        if not shp_files:
            raise ValueError("No .shp found inside the zip")
        shp_path = shp_files[0]

    try:
        features = []
        with fiona.open(shp_path) as src:
            for feat in src:
                geom = feat["geometry"]
                features.append({
                    "type": "Feature",
                    "geometry": dict(geom) if geom else None,
                    "properties": dict(feat["properties"]),
                })
        return {"type": "FeatureCollection", "features": features}
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


def _load_any_fc(path: str) -> Dict[str, Any]:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".geojson", ".json"):
        return _load_geojson_fc(path)
    if ext == ".kml":
        return _load_kml_fc(path)
    if ext in (".shp", ".zip"):
        return _load_shp_fc(path)
    raise ValueError(f"Unsupported GIS format: {ext}")


# ─── Write FeatureCollection → each format ──────────────────────────────────────
def _write_geojson_fc(fc: dict, out_path: str) -> str:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, indent=2)
    return out_path


def _write_kml_fc(fc: dict, out_path: str) -> str:
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>']
    for feat in fc.get("features", []):
        name = str(feat.get("properties", {}).get("name", "Polygon"))
        for ring in _rings_of(feat.get("geometry") or {}):
            coord_str = " ".join(f"{c[0]},{c[1]},0" for c in ring)
            parts.append(
                f"<Placemark><name>{name}</name><Polygon><outerBoundaryIs>"
                f"<LinearRing><coordinates>{coord_str}</coordinates></LinearRing>"
                f"</outerBoundaryIs></Polygon></Placemark>"
            )
    parts.append("</Document></kml>")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return out_path


def _write_shp_zip(fc: dict, base_name: str, out_zip: str) -> str:
    """Write FeatureCollection to a shapefile and bundle components into a zip."""
    import fiona

    features = [f for f in fc.get("features", []) if f.get("geometry")]
    if not features:
        raise ValueError("No geometries to write")

    geom_type = features[0]["geometry"]["type"]

    # Build a property schema from the union of property keys (typed as str for safety).
    prop_keys: Dict[str, str] = {}
    for feat in features:
        for k, v in (feat.get("properties") or {}).items():
            if k not in prop_keys:
                if isinstance(v, bool):
                    prop_keys[k] = "int:1"
                elif isinstance(v, int):
                    prop_keys[k] = "int:18"
                elif isinstance(v, float):
                    prop_keys[k] = "float:24.6"
                else:
                    prop_keys[k] = "str:254"

    schema = {"geometry": geom_type, "properties": prop_keys}
    tmpdir = tempfile.mkdtemp(prefix="shpout_")
    shp_path = os.path.join(tmpdir, f"{base_name}.shp")
    try:
        with fiona.open(shp_path, "w", driver="ESRI Shapefile",
                        crs="EPSG:4326", schema=schema) as dst:
            for feat in features:
                props = {k: (feat.get("properties") or {}).get(k) for k in prop_keys}
                dst.write({"geometry": feat["geometry"], "properties": props})

        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for fn in os.listdir(tmpdir):
                z.write(os.path.join(tmpdir, fn), arcname=fn)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return out_zip


# ─── Public tools (registered in registry) ─────────────────────────────────────
# Cap how many per-polygon rows we inline. Aggregates (count, total area) are
# ALWAYS computed over every polygon; only the detail list is capped so a file
# with hundreds of features doesn't overflow the model's context and get cut
# mid-record (which made the model miscount and report "data tidak lengkap").
MAX_POLYGONS_IN_SUMMARY = 40
# Below this area a polygon is treated as a digitizing artifact, not a real parcel.
DEGENERATE_AREA_HA = 0.0001  # ~1 m²


def _summarize_fc(fc: dict) -> dict:
    feats = fc.get("features", [])
    total_area = 0.0
    items = []
    for feat in feats:
        for ring in _rings_of(feat.get("geometry") or {}):
            a = haversine_area_ha(ring)
            total_area += a
            items.append({
                "name": (feat.get("properties") or {}).get("name", "Unnamed"),
                "area_ha": a,
                "centroid": _centroid(ring),
                "bbox": _bbox(ring),
                "vertex_count": len(ring),
            })
    total_area = round(total_area, 4)
    polygon_count = len(items)
    shown = items[:MAX_POLYGONS_IN_SUMMARY]
    truncated = polygon_count > MAX_POLYGONS_IN_SUMMARY
    mean_area = round(total_area / polygon_count, 4) if polygon_count else 0.0
    total_vertices = sum(x["vertex_count"] for x in items)

    # Degenerate polygons (area below ~1 m²) are digitizing artifacts, not real
    # parcels — pick largest/smallest from valid ones so a 0.0-Ha sliver doesn't
    # get reported as "the smallest parcel".
    valid = [p for p in items if p["area_ha"] > DEGENERATE_AREA_HA]
    degenerate = [p for p in items if p["area_ha"] <= DEGENERATE_AREA_HA]
    pool = valid or items
    largest = max(pool, key=lambda x: x["area_ha"], default=None)
    smallest = min(pool, key=lambda x: x["area_ha"], default=None)

    # Duplicate names (same parcel digitised twice → often the artifact above).
    name_counts = Counter(p["name"] for p in items)
    duplicate_names = sorted(n for n, c in name_counts.items() if c > 1)

    out = {
        "feature_count": len(feats),
        "polygon_count": polygon_count,
        "total_area_ha": total_area,
        "mean_area_ha": mean_area,
        "total_vertices": total_vertices,
        "polygons": shown,
        "polygons_shown": len(shown),
        "polygons_truncated": truncated,
        "degenerate_count": len(degenerate),
        "duplicate_name_count": len(duplicate_names),
    }
    if degenerate:
        out["degenerate_polygons"] = [d["name"] for d in degenerate][:20]
    if duplicate_names:
        out["duplicate_names"] = duplicate_names[:20]
    if largest:
        out["largest_polygon"] = {"name": largest["name"], "area_ha": largest["area_ha"]}
    if smallest:
        out["smallest_polygon"] = {"name": smallest["name"], "area_ha": smallest["area_ha"]}
    # Concise human summary — NOT a JSON dump (a truncated dump misled the model).
    extra = ""
    if largest and smallest:
        extra = (f" Rata-rata {mean_area} Ha; terbesar {largest['name']} ({largest['area_ha']} Ha), "
                 f"terkecil {smallest['name']} ({smallest['area_ha']} Ha).")
    flags = ""
    if degenerate:
        flags += (f" Catatan: {len(degenerate)} poligon berluas ~0 Ha (artefak digitasi, "
                  f"tidak dihitung sbg bidang terkecil).")
    if duplicate_names:
        flags += f" {len(duplicate_names)} nama bidang muncul ganda."
    note = (f" Hanya {len(shown)} dari {polygon_count} poligon yang dirinci di sini; "
            f"agregat (jumlah, total, rata-rata, terbesar, terkecil) sudah mencakup SEMUA {polygon_count} poligon."
            if truncated else "")
    out["text"] = f"{polygon_count} poligon, total luas {total_area} Ha.{extra}{flags}{note}"
    return out


def read_geojson(file_path: str) -> Dict[str, Any]:
    """Read GeoJSON → summary with per-polygon area/centroid/bbox."""
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    try:
        fc = _load_geojson_fc(file_path)
        s = _summarize_fc(fc)
        s.update({"source": file_path, "type": "geojson"})
        return s
    except Exception as e:
        return {"error": str(e), "source": file_path}


def read_shp(file_path: str) -> Dict[str, Any]:
    """Read a Shapefile (.shp with siblings, or a .zip) → summary."""
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    try:
        fc = _load_shp_fc(file_path)
        s = _summarize_fc(fc)
        s.update({"source": file_path, "type": "shp"})
        return s
    except Exception as e:
        return {"error": str(e), "source": file_path}


def write_geojson(filename: str, data: Any) -> Dict[str, Any]:
    """Write a GeoJSON FeatureCollection/Feature/geometry to reports/."""
    try:
        if not filename.lower().endswith((".geojson", ".json")):
            filename += ".geojson"
        if isinstance(data, str):
            data = json.loads(data)
        if data.get("type") != "FeatureCollection":
            if data.get("type") == "Feature":
                data = {"type": "FeatureCollection", "features": [data]}
            else:
                data = {"type": "FeatureCollection",
                        "features": [{"type": "Feature", "geometry": data, "properties": {}}]}
        out = _write_geojson_fc(data, _out_path(filename))
        return {"success": True, "file": out, "filename": os.path.basename(out),
                "size": os.path.getsize(out), "type": "geojson"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_shp(filename: str, data: Any) -> Dict[str, Any]:
    """Write GeoJSON data to a Shapefile bundled as a .zip in reports/."""
    try:
        if isinstance(data, str):
            data = json.loads(data)
        if data.get("type") != "FeatureCollection":
            data = ({"type": "FeatureCollection", "features": [data]}
                    if data.get("type") == "Feature"
                    else {"type": "FeatureCollection",
                          "features": [{"type": "Feature", "geometry": data, "properties": {}}]})
        base = os.path.splitext(os.path.basename(filename))[0]
        out_zip = _out_path(base + ".zip")
        _write_shp_zip(data, base, out_zip)
        return {"success": True, "file": out_zip, "filename": os.path.basename(out_zip),
                "size": os.path.getsize(out_zip), "type": "shp-zip"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def convert_geo(file_path: str, to_format: str, filename: str = None) -> Dict[str, Any]:
    """
    Convert between GIS formats. Input auto-detected from extension
    (.kml/.geojson/.json/.shp/.zip). to_format: 'geojson' | 'kml' | 'shp'.
    """
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    to_format = (to_format or "").lower().lstrip(".")
    try:
        fc = _load_any_fc(file_path)
        base = os.path.splitext(os.path.basename(filename or file_path))[0]
        if to_format in ("geojson", "json"):
            out = _write_geojson_fc(fc, _out_path(base + ".geojson"))
            ftype = "geojson"
        elif to_format == "kml":
            out = _write_kml_fc(fc, _out_path(base + ".kml"))
            ftype = "kml"
        elif to_format in ("shp", "shapefile"):
            out = _write_shp_zip(fc, base, _out_path(base + ".zip"))
            ftype = "shp-zip"
        else:
            return {"error": f"Unsupported target format: {to_format}"}
        return {"success": True, "file": out, "filename": os.path.basename(out),
                "size": os.path.getsize(out), "type": ftype,
                "feature_count": len(fc.get("features", []))}
    except Exception as e:
        return {"success": False, "error": str(e), "source": file_path}
