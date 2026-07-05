"""WeatherPlugin (Bab 59.2 — kategori Weather: data cuaca untuk perencanaan
operasi lapangan/tambang/GIS).

Open-Meteo is free, keyless, and called synchronously via stdlib `urllib` —
same style as `agent/tools/analyzers.py` in the tool registry this plugin
plugs into, and avoids a new dependency (Bab 45.3) for a single HTTP call.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from plugins.base import PluginInterface

from . import config

_MANIFEST_PATH = Path(__file__).parent / "manifest.json"


class WeatherPlugin(PluginInterface):
    def __init__(self) -> None:
        manifest = json.loads(_MANIFEST_PATH.read_text())
        self.name = manifest["name"]
        self.version = manifest["version"]
        self.description = manifest["description"]
        self.permission_action = manifest["permission_action"]
        self._manifest = manifest

    def manifest(self) -> dict[str, Any]:
        return dict(self._manifest)

    def _fetch(self, url: str) -> dict[str, Any]:
        """Split out so tests can monkeypatch the network call directly."""
        with urllib.request.urlopen(url, timeout=config.TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode())

    def execute(self, latitude: float, longitude: float, **_: Any) -> dict[str, Any]:
        params = urllib.parse.urlencode({
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,precipitation,wind_speed_10m,weather_code",
        })
        url = f"{config.BASE_URL}?{params}"
        try:
            data = self._fetch(url)
            current = data.get("current", {})
            return {
                "success": True,
                "latitude": latitude,
                "longitude": longitude,
                "temperature_c": current.get("temperature_2m"),
                "precipitation_mm": current.get("precipitation"),
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "weather_code": current.get("weather_code"),
                "source": "open-meteo.com",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
