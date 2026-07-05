"""Integration tests for /api/v1/plugins/* (Bab 59).

No database involved (`registry/plugin_registry.py`'s enabled state is
in-memory) — just a real ASGI client against the real app + real RBAC via
`API_KEYS`, same identity-simulation pattern as test_automation_api.py.
"""
import pytest
from httpx import ASGITransport, AsyncClient

import registry.plugin_registry as plugin_registry


@pytest.fixture(autouse=True)
def _api_keys(monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "adminkey:admin,userkey:user")


@pytest.fixture(autouse=True)
def _reset_plugin_state():
    yield
    plugin_registry._enabled["weather"] = True


@pytest.fixture
async def client():
    from api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _as(key: str) -> dict:
    return {"X-API-Key": key}


async def test_list_plugins_includes_weather(client):
    res = await client.get("/api/v1/plugins", headers=_as("userkey"))
    assert res.status_code == 200
    weather = next(p for p in res.json()["plugins"] if p["name"] == "weather")
    assert weather["enabled"] is True


async def test_toggle_denied_for_non_admin(client):
    res = await client.patch("/api/v1/plugins/weather", json={"enabled": False}, headers=_as("userkey"))
    assert res.status_code == 403


async def test_toggle_allowed_for_admin(client):
    res = await client.patch("/api/v1/plugins/weather", json={"enabled": False}, headers=_as("adminkey"))
    assert res.status_code == 200
    assert res.json()["enabled"] is False

    list_res = await client.get("/api/v1/plugins", headers=_as("userkey"))
    weather = next(p for p in list_res.json()["plugins"] if p["name"] == "weather")
    assert weather["enabled"] is False


async def test_toggle_unknown_plugin_404(client):
    res = await client.patch("/api/v1/plugins/does-not-exist", json={"enabled": False}, headers=_as("adminkey"))
    assert res.status_code == 404
