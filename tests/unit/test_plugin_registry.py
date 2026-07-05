"""Unit tests for registry/plugin_registry.py (Bab 59) — in-memory catalog."""
import registry.plugin_registry as plugin_registry


def teardown_function():
    # Reset shared module state so tests don't leak into each other (or
    # into other test files that happen to import this module first).
    plugin_registry._enabled["weather"] = True


def test_list_plugins_includes_weather_enabled_by_default():
    plugins = plugin_registry.list_plugins()
    weather = next(p for p in plugins if p["name"] == "weather")
    assert weather["enabled"] is True
    assert weather["permission_action"] == "plugin:weather"


def test_get_returns_instance_when_enabled():
    assert plugin_registry.get("weather") is not None


def test_set_enabled_false_disables_and_get_returns_none():
    result = plugin_registry.set_enabled("weather", False)
    assert result["enabled"] is False
    assert plugin_registry.is_enabled("weather") is False
    assert plugin_registry.get("weather") is None


def test_set_enabled_unknown_plugin_returns_none():
    assert plugin_registry.set_enabled("does-not-exist", True) is None


def test_is_enabled_false_for_unknown_plugin():
    assert plugin_registry.is_enabled("does-not-exist") is False
