"""Prompt Injection Guard (MASTER_INSTRUCTION.md Bab 30) — detect and neutralize.

Heuristic, pattern-based (Bab 45.3 — no ML classifier dependency, and a real
one would need a model + inference cost this codebase doesn't otherwise take
on). Bab 30 rule 1 requires every external LLM call to pass through this
before leaving the system boundary — wired into ``agents/generic_agent.py``,
the single choke point every role's dispatch already goes through.

Two thresholds, matching Bab 30's own wording ("mendeteksi dan
menetralisir"): above ``PROMPT_GUARD_SUSPICIOUS_THRESHOLD`` the matched spans
are neutralized (not blocked) so a false positive doesn't kill a legitimate
request; only above ``PROMPT_GUARD_BLOCK_THRESHOLD`` does the caller treat the
dispatch as failed outright.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.utils.logger import get_logger

logger = get_logger(__name__)

# (pattern, weight, label) — weight in [0, 1], summed across matches and
# capped at 1.0. Patterns target instruction-override / jailbreak / prompt-
# exfiltration phrasing, not just single keywords, to keep false positives
# on ordinary text low.
_PATTERNS: list[tuple[re.Pattern, float, str]] = [
    (re.compile(r"\bignore\s+(all\s+|the\s+)?(previous|above|prior)\s+instructions?\b", re.I), 0.6, "ignore_instructions"),
    (re.compile(r"\bdisregard\s+(your|the|all)\s+(instructions?|system\s*prompt|rules)\b", re.I), 0.6, "disregard_instructions"),
    (re.compile(r"\b(reveal|print|show|output)\s+(your\s+)?(system\s*prompt|initial\s+instructions?|hidden\s+prompt)\b", re.I), 0.7, "prompt_exfiltration"),
    (re.compile(r"\bdo\s+anything\s+now\b|\bDAN\s+mode\b|\bjailbreak(ed|ing)?\b", re.I), 0.7, "jailbreak_keyword"),
    (re.compile(r"\bpretend\s+(you\s+are\s+not|to\s+not\s+be)\s+an?\s+ai\b", re.I), 0.5, "identity_override"),
    (re.compile(r"\bnew\s+instructions?\s*:\s*\S", re.I), 0.5, "new_instructions"),
    (re.compile(r"^\s*(system|assistant)\s*:\s*\S", re.I | re.M), 0.5, "fake_role_turn"),
    (re.compile(r"\boverride\s+(your\s+)?(system\s*prompt|configuration|rules)\b", re.I), 0.6, "override_config"),
    (re.compile(r"\bno\s+(restrictions?|limitations?|filters?)\s+(apply|now)\b", re.I), 0.4, "no_restrictions"),
    (re.compile(r"\bact\s+as\s+if\s+you\s+(have\s+no|had\s+no)\s+(restrictions?|rules|guidelines)\b", re.I), 0.6, "unrestricted_roleplay"),
]


@dataclass(frozen=True)
class GuardResult:
    """Prompt-injection risk assessment for one piece of text."""

    score: float
    matches: list[str] = field(default_factory=list)
    sanitized_text: str = ""
    suspicious: bool = False
    blocked: bool = False


def check(text: str) -> GuardResult:
    """Score ``text`` for prompt-injection risk and produce a neutralized version."""
    from api.config import settings

    matches: list[str] = []
    score = 0.0
    sanitized = text
    for pattern, weight, label in _PATTERNS:
        if pattern.search(sanitized):
            matches.append(label)
            score += weight
            sanitized = pattern.sub("[neutralized]", sanitized)
    score = min(score, 1.0)

    result = GuardResult(
        score=score,
        matches=matches,
        sanitized_text=sanitized,
        suspicious=score >= settings.PROMPT_GUARD_SUSPICIOUS_THRESHOLD,
        blocked=score >= settings.PROMPT_GUARD_BLOCK_THRESHOLD,
    )
    if matches:
        logger.warning("prompt_guard.matched", score=score, matches=matches, blocked=result.blocked)
    return result
