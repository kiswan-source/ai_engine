"""Apply + review loop for the Continuous Improvement Engine (Fase 7, DCF
v5 mandate: "Semua improvement: dianalisis, diuji, divalidasi, memiliki
rollback").

Only ``ENABLE_AUTONOMOUS_IMPROVEMENT=True`` deployments ever call
:func:`apply_recommendation` for real — see ``api/config.py``'s docstring
on that flag for why it defaults off. Everything here is written to be
safe regardless: a narrow, hard-bounded settings whitelist
(:data:`WHITELISTED_SETTINGS`), a dirty-tree safety check
(``improvement/git_ops.py::safe_to_commit``) immediately before any
commit, and every applied change scheduled for a later automatic review
that reverts it (a normal ``git revert``, never a reset) if the problem
it was meant to fix hasn't actually improved.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from improvement import git_ops, ledger
from improvement.engine import ImprovementEngine
from improvement.models import ImprovementAction, ImprovementRecommendation

# The ONLY setting this pass may auto-adjust, and the ONE file it lives in.
# Expanding this list is a separate, deliberate decision — not something to
# grow quietly as new recommendation categories are added to engine.py.
WHITELISTED_SETTINGS = {
    "CONFIDENCE_THRESHOLD_DEFAULT": "config/agents.yaml",
}


def _repo_root() -> str:
    from api.config import settings

    return getattr(settings, "IMPROVEMENT_REPO_PATH", None) or str(Path(__file__).resolve().parent.parent)


def _read_yaml_value(path: Path, key: str) -> float:
    pattern = re.compile(rf"^{re.escape(key)}:\s*([0-9.]+)\s*$", re.MULTILINE)
    match = pattern.search(path.read_text())
    if match is None:
        raise ValueError(f"{key} not found in {path}")
    return float(match.group(1))


def _write_yaml_value(path: Path, key: str, value: float) -> None:
    """Replace exactly one `KEY: <value>` line via regex, not a full YAML
    parse/re-serialize — preserves every comment and the rest of the
    file's formatting untouched, so a git diff shows exactly one line
    changed, nothing incidental."""
    pattern = re.compile(rf"^({re.escape(key)}:\s*)[0-9.]+(\s*)$", re.MULTILINE)
    text = path.read_text()
    new_text, count = pattern.subn(rf"\g<1>{value}\g<2>", text)
    if count != 1:
        raise ValueError(f"expected exactly one {key} line in {path}, found {count}")
    path.write_text(new_text)


def apply_recommendation(rec: ImprovementRecommendation, repo_path: str | None = None) -> ImprovementAction | None:
    """Turn `rec` into a real, committed config change — or return `None`
    without doing anything if it isn't a whitelisted, in-bounds,
    safe-to-commit change. Never raises for an ordinary "can't apply this
    one" reason; only a git/filesystem failure propagates."""
    from api.config import settings

    if rec.setting not in WHITELISTED_SETTINGS or rec.suggested_value is None:
        return None
    if not (settings.IMPROVEMENT_CONFIDENCE_MIN <= rec.suggested_value <= settings.IMPROVEMENT_CONFIDENCE_MAX):
        return None

    repo_path = repo_path or _repo_root()
    relative_path = WHITELISTED_SETTINGS[rec.setting]
    config_path = Path(repo_path) / relative_path

    old_value = _read_yaml_value(config_path, rec.setting)

    git_ops.safe_to_commit(repo_path, relative_path)  # raises DirtyTreeError — caller decides how to handle
    _write_yaml_value(config_path, rec.setting, rec.suggested_value)
    commit_sha = git_ops.commit_file(
        repo_path, relative_path,
        f"improvement: auto-adjust {rec.setting} {old_value} -> {rec.suggested_value}\n\n"
        f"Recommendation {rec.id}: {rec.suggestion}",
    )

    action = ImprovementAction(
        recommendation_id=rec.id,
        setting=rec.setting,
        old_value=old_value,
        new_value=rec.suggested_value,
        commit_sha=commit_sha,
        review_after=time.time() + settings.IMPROVEMENT_REVIEW_WINDOW_SECONDS,
    )
    ledger.record_action_applied(action)
    return action


async def review_pending_actions(engine: ImprovementEngine, repo_path: str | None = None) -> list[ImprovementAction]:
    """For every applied action whose review window has elapsed, re-check
    whether the problem it targeted is still outside the healthy band —
    if so, revert; otherwise, keep. A single post-hoc check, not a proper
    controlled comparison — documented as a known limitation, not claimed
    to be more rigorous than it is."""
    from api.config import settings

    repo_path = repo_path or _repo_root()
    now = time.time()
    processed: list[ImprovementAction] = []

    for action in ledger.pending_actions():
        if now < action.review_after:
            continue

        rate = await engine.current_escalate_rate()
        still_bad = (
            rate is not None
            and (rate > settings.IMPROVEMENT_ESCALATE_RATE_HIGH or rate < settings.IMPROVEMENT_ESCALATE_RATE_LOW)
        )

        if still_bad:
            revert_sha = git_ops.revert_commit(repo_path, action.commit_sha)
            action = ImprovementAction(
                id=action.id, recommendation_id=action.recommendation_id, created_at=action.created_at,
                setting=action.setting, old_value=action.old_value, new_value=action.new_value,
                commit_sha=action.commit_sha, review_after=action.review_after,
                reviewed_at=now, outcome="reverted", revert_commit_sha=revert_sha,
            )
        else:
            action = ImprovementAction(
                id=action.id, recommendation_id=action.recommendation_id, created_at=action.created_at,
                setting=action.setting, old_value=action.old_value, new_value=action.new_value,
                commit_sha=action.commit_sha, review_after=action.review_after,
                reviewed_at=now, outcome="kept",
            )
        ledger.record_action_reviewed(action)
        processed.append(action)

    return processed
