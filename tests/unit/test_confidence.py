"""Unit tests for Confidence Scoring (Bab 28)."""
import pytest

from agents.base_agent import AgentResult
from memory.reflection_memory import ReflectionMemory
from memory.stores import InMemoryListStore
from orchestrator import confidence as confidence_module
from orchestrator.confidence import ConfidenceScorer, threshold_for


def _result(confidence: float, role: str = "writer") -> AgentResult:
    return AgentResult(
        output="hasil",
        confidence=confidence,
        trace_id="t1",
        provider_used="stub",
        model_used="stub-m",
        role=role,
    )


@pytest.mark.asyncio
async def test_score_with_only_self_reported_signal():
    scorer = ConfidenceScorer()
    breakdown = await scorer.score(_result(0.8))
    assert breakdown.score == 0.8
    assert breakdown.history is None
    assert breakdown.agreement is None


@pytest.mark.asyncio
async def test_score_blends_history_from_reflection_memory():
    memory = ReflectionMemory(InMemoryListStore())
    await memory.record(role="writer", task_id="a", trace_id="t0", success=True, score=0.4)
    await memory.record(role="writer", task_id="b", trace_id="t0", success=True, score=0.6)

    scorer = ConfidenceScorer()
    breakdown = await scorer.score(_result(0.8), memory=memory)

    assert breakdown.history == pytest.approx(0.5)
    # weighted blend of self-reported (0.8) and history (0.5), renormalized over
    # just those two signals' weights (no agreement/guardrail signal here).
    w_self, w_history = confidence_module._W_SELF_REPORTED, confidence_module._W_HISTORY
    expected = (w_self * 0.8 + w_history * 0.5) / (w_self + w_history)
    assert breakdown.score == pytest.approx(round(expected, 4))


@pytest.mark.asyncio
async def test_score_ignores_history_for_role_with_no_entries():
    memory = ReflectionMemory(InMemoryListStore())
    await memory.record(role="analyst", task_id="a", trace_id="t0", success=True, score=0.9)

    scorer = ConfidenceScorer()
    breakdown = await scorer.score(_result(0.8, role="writer"), memory=memory)

    assert breakdown.history is None
    assert breakdown.score == 0.8


@pytest.mark.asyncio
async def test_score_blends_agreement_rate():
    scorer = ConfidenceScorer()
    breakdown = await scorer.score(_result(0.6), agreement_rate=1.0)
    w_self, w_agree = confidence_module._W_SELF_REPORTED, confidence_module._W_AGREEMENT
    expected = (w_self * 0.6 + w_agree * 1.0) / (w_self + w_agree)
    assert breakdown.score == pytest.approx(round(expected, 4))
    assert breakdown.agreement == 1.0


async def test_score_blends_guardrail_signal():
    scorer = ConfidenceScorer()
    breakdown = await scorer.score(_result(0.6), guardrail_score=0.5)
    w_self, w_guard = confidence_module._W_SELF_REPORTED, confidence_module._W_GUARDRAIL
    expected = (w_self * 0.6 + w_guard * 0.5) / (w_self + w_guard)
    assert breakdown.score == pytest.approx(round(expected, 4))
    assert breakdown.guardrail == 0.5


async def test_score_defaults_guardrail_from_result():
    result = AgentResult(
        output="hasil", confidence=0.6, trace_id="t1", provider_used="stub",
        model_used="stub-m", role="writer", guardrail_score=0.9,
    )
    scorer = ConfidenceScorer()
    breakdown = await scorer.score(result)
    assert breakdown.guardrail == 0.9


def test_threshold_for_default_and_high_risk():
    assert threshold_for() < threshold_for("high")
    assert threshold_for("default") == threshold_for()
