"""Unit tests for WeatherPlugin (Bab 59.2) — network mocked via `_fetch` (Bab 12.3)."""
from plugins.weather.plugin import WeatherPlugin


def test_manifest_matches_manifest_json():
    plugin = WeatherPlugin()
    manifest = plugin.manifest()
    assert manifest["name"] == "weather"
    assert manifest["permission_action"] == "plugin:weather"
    assert "current_weather" in manifest["capabilities"]


def test_execute_returns_success_shape(monkeypatch):
    plugin = WeatherPlugin()
    monkeypatch.setattr(
        plugin,
        "_fetch",
        lambda url: {
            "current": {
                "temperature_2m": 27.4,
                "precipitation": 0.0,
                "wind_speed_10m": 8.1,
                "weather_code": 1,
            }
        },
    )
    result = plugin.execute(latitude=-6.2, longitude=106.8)
    assert result["success"] is True
    assert result["temperature_c"] == 27.4
    assert result["source"] == "open-meteo.com"


def test_execute_returns_failure_shape_on_network_error(monkeypatch):
    plugin = WeatherPlugin()

    def _boom(url):
        raise OSError("network unreachable")

    monkeypatch.setattr(plugin, "_fetch", _boom)
    result = plugin.execute(latitude=0, longitude=0)
    assert result["success"] is False
    assert "network unreachable" in result["error"]
