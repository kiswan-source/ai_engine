"""Unit tests for the registry layer (MASTER_INSTRUCTION.md Bab 19-21)."""
import pytest

from providers import OllamaProvider, create_for_role
from registry import model_registry, provider_registry
from registry.model_registry import ROLES, ModelAssignment


# ─── Provider Registry ────────────────────────────────────────────────────────

def test_ollama_always_enabled():
    cfg = provider_registry.get_provider_config("ollama")
    assert cfg is not None
    assert cfg.enabled is True
    assert cfg.requires_api_key is False


def test_cloud_disabled_without_key(monkeypatch):
    monkeypatch.setattr(provider_registry.settings, "OPENAI_API_KEY", "")
    assert provider_registry.get_provider_config("openai").enabled is False
    assert "openai" not in provider_registry.list_enabled_providers()


def test_cloud_enabled_with_key(monkeypatch):
    monkeypatch.setattr(provider_registry.settings, "ANTHROPIC_API_KEY", "sk-ant-xxx")
    assert provider_registry.get_provider_config("claude").enabled is True
    assert "claude" in provider_registry.list_enabled_providers()


def test_list_providers_contains_all_four():
    assert set(provider_registry.list_providers()) == {"ollama", "openai", "claude", "gemini"}


def test_unknown_provider_config_is_none():
    assert provider_registry.get_provider_config("nope") is None


# ─── Model Registry ───────────────────────────────────────────────────────────

def test_every_role_resolves():
    for role in ROLES:
        assignment = model_registry.resolve(role)
        assert isinstance(assignment, ModelAssignment)
        assert assignment.role == role
        # Fallback is always local so the platform survives without cloud keys.
        assert assignment.fallback_provider == "ollama"


def test_local_roles_use_ollama_primary():
    for role in ("memory", "guardrail", "prompt_optimizer", "tool", "cost_optimizer"):
        assert model_registry.resolve(role).provider == "ollama"


def test_cloud_roles_have_cloud_primary():
    assert model_registry.resolve("planner").provider == "openai"
    assert model_registry.resolve("analyst").provider == "claude"
    assert model_registry.resolve("research").provider == "gemini"


def test_resolve_unknown_role_raises():
    with pytest.raises(KeyError):
        model_registry.resolve("emperor")


# ─── Role-based factory + fallback (Bab 54) ───────────────────────────────────

def test_create_for_role_falls_back_to_ollama_without_key(monkeypatch):
    # No cloud keys configured -> planner (primary openai) degrades to local.
    monkeypatch.setattr(provider_registry.settings, "OPENAI_API_KEY", "")
    prov = create_for_role("planner")
    assert isinstance(prov, OllamaProvider)


def test_create_for_role_prefer_fallback_forces_ollama():
    prov = create_for_role("analyst", prefer_fallback=True)
    assert isinstance(prov, OllamaProvider)


def test_local_role_uses_ollama_directly():
    prov = create_for_role("memory")
    assert isinstance(prov, OllamaProvider)
