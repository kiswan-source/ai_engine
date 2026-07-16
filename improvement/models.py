"""Domain objects for the Continuous Improvement Engine (Fase 7, DCF v5
mandate). See ``improvement/engine.py`` for the analysis that produces
``ImprovementRecommendation``s and ``improvement/apply.py`` for what turns
one into an ``ImprovementAction``.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ImprovementRecommendation:
    """One detected improvement candidate — evidence-backed, not guessed.

    ``setting``/``suggested_value`` are only meaningful for recommendations
    that map to a concrete, whitelisted config change (see
    ``improvement/apply.py::WHITELISTED_SETTINGS``); a recommendation that
    doesn't (e.g. "role X's lessons keep mentioning the same failure mode")
    still gets recorded — for a human to read — but can never be
    auto-applied.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)
    category: str = ""  # e.g. "confidence_threshold", "role_error_rate"
    severity: str = "low"  # "low" | "medium" | "high"
    evidence: dict[str, Any] = field(default_factory=dict)
    suggestion: str = ""
    setting: str | None = None
    suggested_value: float | None = None


@dataclass(frozen=True)
class ImprovementAction:
    """One applied (or reverted) change — the record that makes an
    auto-applied recommendation reviewable and reversible, not a silent
    self-modification."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    recommendation_id: str = ""
    created_at: float = field(default_factory=time.time)
    setting: str = ""
    old_value: float = 0.0
    new_value: float = 0.0
    commit_sha: str = ""
    review_after: float = 0.0  # unix timestamp — review_pending_actions() acts once this has passed
    reviewed_at: float | None = None
    outcome: str | None = None  # None (pending) | "kept" | "reverted"
    revert_commit_sha: str | None = None


def to_json_dict(obj: ImprovementRecommendation | ImprovementAction) -> dict[str, Any]:
    return asdict(obj)
