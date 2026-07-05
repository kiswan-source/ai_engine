"""Plugin Registry (MASTER_INSTRUCTION.md Bab 59) — an explicit, deterministic
catalog, not a filesystem auto-scan (Bab 45.3 — an explicit dict is just as
easy to extend and far more auditable than import-everything-under-plugins/).

Enabled state is in-memory only for this first pass (mirrors the
HashStore-pluggable-with-in-memory-default pattern used before Tahap 9 wired
Redis for the Circuit Breaker) — a process restart resets every plugin back
to enabled, an accepted gap for now, not a hidden one.
"""
from __future__ import annotations

from plugins.base import PluginInterface
from plugins.weather.plugin import WeatherPlugin

_AVAILABLE: dict[str, PluginInterface] = {
    "weather": WeatherPlugin(),
}

_enabled: dict[str, bool] = {name: True for name in _AVAILABLE}


def list_plugins() -> list[dict]:
    return [{**plugin.manifest(), "enabled": _enabled[name]} for name, plugin in _AVAILABLE.items()]


def set_enabled(name: str, enabled: bool) -> dict | None:
    if name not in _AVAILABLE:
        return None
    _enabled[name] = enabled
    return {**_AVAILABLE[name].manifest(), "enabled": enabled}


def is_enabled(name: str) -> bool:
    return _enabled.get(name, False)


def get(name: str) -> PluginInterface | None:
    """The plugin instance if it exists AND is enabled — `None` otherwise."""
    return _AVAILABLE.get(name) if _enabled.get(name) else None
