"""Prompt Versioning (MASTER_INSTRUCTION.md Bab 51).

Prompts live as versioned files at ``prompts/<agent>/<name>_v<N>.md`` with
a YAML frontmatter metadata header (agent, version, created, author,
status). The active version is a decision the CALLER states explicitly
(Bab 51.2: "didaftarkan secara eksplisit ... bukan disimpulkan dari nomor
tertinggi secara otomatis") — this loader never guesses which version is
active, it only loads the one it's told to.
"""
from pathlib import Path

PROMPTS_ROOT = Path(__file__).resolve().parent


class PromptNotFoundError(FileNotFoundError):
    pass


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].strip()
    return text.strip()


def load_prompt(agent: str, name: str, version: int) -> str:
    path = PROMPTS_ROOT / agent / f"{name}_v{version}.md"
    if not path.is_file():
        raise PromptNotFoundError(f"prompt not found: {path}")
    return _strip_frontmatter(path.read_text(encoding="utf-8"))
