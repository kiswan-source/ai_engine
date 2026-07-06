"""Unit tests for prompts/loader.py (Bab 51 Prompt Versioning, Tahap 37)."""
import pytest

from prompts.loader import PromptNotFoundError, load_prompt


def test_load_prompt_strips_frontmatter_and_returns_body():
    text = load_prompt("chat", "system", version=1)
    assert not text.startswith("---")
    assert "agent: chat" not in text
    assert "ATURAN:" in text


def test_load_prompt_missing_file_raises():
    with pytest.raises(PromptNotFoundError):
        load_prompt("chat", "does_not_exist", version=99)


def test_load_prompt_missing_file_is_a_file_not_found_error():
    with pytest.raises(FileNotFoundError):
        load_prompt("nonexistent_agent", "x", version=1)


def test_load_prompt_without_frontmatter_still_loads(tmp_path, monkeypatch):
    import prompts.loader as loader_module

    agent_dir = tmp_path / "plainagent"
    agent_dir.mkdir()
    (agent_dir / "plain_v1.md").write_text("Just a body, no frontmatter.", encoding="utf-8")
    monkeypatch.setattr(loader_module, "PROMPTS_ROOT", tmp_path)

    assert loader_module.load_prompt("plainagent", "plain", version=1) == "Just a body, no frontmatter."
