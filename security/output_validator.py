"""Output Validation (MASTER_INSTRUCTION.md Bab 30) — policy/format check on model output.

Runs after every generation (``agents/generic_agent.py``), before the result
reaches a workflow or a user. Its score doubles as the fourth Confidence
Scoring signal Bab 28's table names ("Hasil validasi guardrail dan output
validator") — ADR-0007 (Tahap 4) left that slot explicitly unfilled pending
this module; :func:`orchestrator.confidence.ConfidenceScorer.score` now
accepts it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import pii_detector

_MIN_LENGTH = 2  # shorter than this counts as an empty/non-answer
_TEMPLATE_ARTIFACT_RE = re.compile(r"\{\{.*?\}\}|\[\[.*?\]\]|<\|.*?\|>")

# Each violation knocks this much off a perfect score (floored at 0.0) — a
# fixed, simple scale rather than per-violation weights, since these are
# independent structural checks, not a nuanced content-quality judgement.
_PENALTY_PER_VIOLATION = 0.3


@dataclass(frozen=True)
class ValidationResult:
    """Output policy check result — ``score`` blends into Confidence Scoring (Bab 28)."""

    score: float
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def validate(text: str, finish_reason: str | None = None) -> ValidationResult:
    """Check ``text`` against output policy: emptiness, truncation, leaked PII, template artifacts."""
    violations: list[str] = []

    if len(text.strip()) < _MIN_LENGTH:
        violations.append("empty_or_too_short")

    if finish_reason in ("length", "MAX_TOKENS"):
        violations.append("truncated")

    if _TEMPLATE_ARTIFACT_RE.search(text):
        violations.append("unresolved_template_artifact")

    if pii_detector.detect(text):
        violations.append("pii_leak")

    score = max(0.0, 1.0 - _PENALTY_PER_VIOLATION * len(violations))
    return ValidationResult(score=score, violations=violations)
