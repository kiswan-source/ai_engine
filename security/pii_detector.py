"""PII Detection & Redaction (MASTER_INSTRUCTION.md Bab 30).

Regex-based, dependency-free (Bab 45.3) detection of common personal-data
categories, including an Indonesian-context phone/NIK pattern alongside the
generic ones. Bab 30's table scopes redaction to "sebelum dikirim ke
provider eksternal" — ``agents/generic_agent.py`` only redacts for cloud
providers, never for Ollama (local, not leaving the system).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS: dict[str, re.Pattern] = {
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "PHONE_ID": re.compile(r"\b(?:\+62|62|0)8[1-9][0-9]{6,10}\b"),
    "CREDIT_CARD": re.compile(r"\b\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}\b"),
    "NIK_ID": re.compile(r"\b\d{16}\b"),
    "IPV4": re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"),
}


@dataclass(frozen=True)
class PIIMatch:
    """One detected span of personal data."""

    category: str
    text: str
    start: int
    end: int


def detect(text: str) -> list[PIIMatch]:
    """Find every PII span in ``text``, across all known categories, in order."""
    matches: list[PIIMatch] = []
    for category, pattern in _PATTERNS.items():
        for m in pattern.finditer(text):
            matches.append(PIIMatch(category=category, text=m.group(0), start=m.start(), end=m.end()))
    matches.sort(key=lambda m: m.start)
    return matches


def redact(text: str, categories: tuple[str, ...] | None = None) -> str:
    """Replace every detected PII span with a ``[<CATEGORY>_REDACTED]`` placeholder.

    Args:
        categories: Restrict redaction to these categories; ``None`` redacts everything.
    """
    matches = detect(text)
    if categories:
        matches = [m for m in matches if m.category in categories]
    if not matches:
        return text
    out = text
    for m in sorted(matches, key=lambda m: m.start, reverse=True):
        out = out[: m.start] + f"[{m.category}_REDACTED]" + out[m.end :]
    return out
