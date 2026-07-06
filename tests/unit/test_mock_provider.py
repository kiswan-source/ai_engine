"""Unit tests for MockProvider (Bab 68 Backlog Prioritas 16, Tahap 36
Simulation Mode) — deterministic, zero-network, zero-cost stand-in for a
real provider.
"""
from providers.base_provider import GenerationParams
from providers.mock_provider import MockProvider
from telemetry.cost_tracker import price_for


async def test_generate_returns_simulated_marker_and_stop_finish_reason():
    provider = MockProvider()
    resp = await provider.generate("Ringkasan survei lapangan", GenerationParams())

    assert "[SIMULASI]" in resp.text
    assert "Ringkasan survei lapangan" in resp.text
    assert resp.finish_reason == "stop"
    assert resp.provider == "mock"


async def test_generate_never_truncates_confidence():
    """finish_reason must be "stop", not "length" — agents/generic_agent.py's
    _estimate_confidence treats a truncated reason as lower confidence, and a
    simulated run should read as a normal success, not a degraded one."""
    provider = MockProvider()
    resp = await provider.generate("x", GenerationParams())
    assert resp.finish_reason not in ("length", "MAX_TOKENS")


async def test_health_check_is_always_true():
    assert await MockProvider().health_check() is True


async def test_stream_yields_text_then_done():
    chunks = [c async for c in MockProvider().stream("halo", GenerationParams())]
    assert chunks[-1].done is True
    assert "[SIMULASI]" in chunks[0].text


def test_mock_provider_has_zero_cost_by_default():
    """Not added to telemetry/cost_tracker.py's PRICING table — falls
    through to _DEFAULT_PRICE, same as any unknown/local model."""
    assert price_for("mock", "mock-model") == (0.0, 0.0)
