"""Unit tests for Configuration Center (Bab 68 Backlog Prioritas 7,
Tahap 38) — config/*.yaml as a settings source layered under env vars.
"""
from pathlib import Path

import pytest
import yaml
from pydantic_settings import SettingsConfigDict

from api.config import CONFIG_DIR, Settings


def test_env_var_overrides_yaml_value(monkeypatch):
    monkeypatch.setenv("REFLECTION_MAX_ITERATIONS", "9")
    s = Settings()
    assert s.REFLECTION_MAX_ITERATIONS == 9


def test_yaml_file_is_consulted_for_a_field_with_no_env_var(tmp_path, monkeypatch):
    monkeypatch.delenv("CONFIDENCE_THRESHOLD_DEFAULT", raising=False)
    yaml_path = tmp_path / "agents.yaml"
    yaml_path.write_text("CONFIDENCE_THRESHOLD_DEFAULT: 0.42\n", encoding="utf-8")

    class TestSettings(Settings):
        model_config = SettingsConfigDict(
            env_file=None,
            extra="ignore",
            yaml_file=[yaml_path],
        )

    assert TestSettings().CONFIDENCE_THRESHOLD_DEFAULT == 0.42


def test_missing_yaml_files_fall_back_to_class_defaults(monkeypatch):
    monkeypatch.delenv("CONFIDENCE_THRESHOLD_DEFAULT", raising=False)

    class TestSettings(Settings):
        model_config = SettingsConfigDict(
            env_file=None,
            extra="ignore",
            yaml_file=[Path("/nonexistent/does_not_exist.yaml")],
        )

    assert TestSettings().CONFIDENCE_THRESHOLD_DEFAULT == 0.6


def test_config_dir_points_at_real_yaml_files():
    assert CONFIG_DIR.name == "config"
    for name in ("providers", "agents", "workflow", "security", "memory", "budget"):
        assert (CONFIG_DIR / f"{name}.yaml").is_file()


def test_settings_singleton_values_unchanged_by_yaml_migration():
    from api.config import settings

    assert settings.CONFIDENCE_THRESHOLD_DEFAULT == 0.6
    assert settings.RAG_CHUNK_SIZE == 800
    assert settings.COST_BUDGET_DAILY == 50.0
    assert settings.OLLAMA_NUM_CTX == 16384
    assert settings.CIRCUIT_PROVIDER_OVERRIDES == ""


@pytest.mark.parametrize(
    "filename",
    ["providers.yaml", "agents.yaml", "workflow.yaml", "security.yaml", "memory.yaml", "budget.yaml"],
)
def test_no_secret_shaped_keys_in_config_yaml(filename):
    """Checks actual YAML key: value pairs, not prose in comments (this
    file's own header comments legitimately mention API_KEY/SECRET_KEY by
    name to explain why they're excluded)."""
    text = (CONFIG_DIR / filename).read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    forbidden_keys = {"SECRET_KEY", "DATABASE_URL", "REDIS_URL", "API_KEYS",
                       "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"}
    leaked = forbidden_keys & data.keys()
    assert not leaked, f"{filename} must not define secret keys: {leaked}"
