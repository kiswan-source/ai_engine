"""Unit tests for the Circuit Breaker (Bab 55) + its Dispatcher integration.

State-machine tests drive a fake clock (no sleeping); dispatcher tests reuse
the StubAgent pattern from test_orchestrator.py — no provider/network calls.
"""
import pytest

from agents.base_agent import AgentResult, BaseAgent, Task
from orchestrator.dispatcher import Dispatcher
from orchestrator.routing_engine import RoutingEngine
from providers.circuit_breaker import (
    BreakerConfig,
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitState,
    parse_overrides,
)
from providers.exceptions import ProviderError
from registry.agent_registry import AgentRegistry


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_breaker(threshold=3, timeout=30.0, trials=1, clock=None):
    return CircuitBreaker(
        "stub",
        BreakerConfig(failure_threshold=threshold, recovery_timeout=timeout, trial_requests=trials),
        clock=clock or FakeClock(),
    )


# ─── State machine (Bab 55.2) ─────────────────────────────────────────────────

async def test_starts_closed_and_allows():
    breaker = make_breaker()
    assert await breaker.state() == CircuitState.CLOSED
    assert await breaker.allow() is True


async def test_opens_after_threshold_consecutive_failures():
    breaker = make_breaker(threshold=3)
    for _ in range(2):
        await breaker.record_failure()
    assert await breaker.state() == CircuitState.CLOSED  # below threshold
    await breaker.record_failure()
    assert await breaker.state() == CircuitState.OPEN
    assert await breaker.allow() is False


async def test_success_resets_consecutive_failure_count():
    breaker = make_breaker(threshold=3)
    await breaker.record_failure()
    await breaker.record_failure()
    await breaker.record_success()  # breaks the run
    await breaker.record_failure()
    await breaker.record_failure()
    assert await breaker.state() == CircuitState.CLOSED  # 2 < 3 again


async def test_open_transitions_to_half_open_after_recovery_timeout():
    clock = FakeClock()
    breaker = make_breaker(threshold=1, timeout=30.0, clock=clock)
    await breaker.record_failure()
    assert await breaker.allow() is False  # still open
    clock.advance(31)
    assert await breaker.allow() is True  # admitted as trial
    assert await breaker.state() == CircuitState.HALF_OPEN


async def test_half_open_trial_success_closes():
    clock = FakeClock()
    breaker = make_breaker(threshold=1, timeout=30.0, trials=1, clock=clock)
    await breaker.record_failure()
    clock.advance(31)
    assert await breaker.allow() is True
    await breaker.record_success()
    assert await breaker.state() == CircuitState.CLOSED
    assert await breaker.allow() is True


async def test_half_open_trial_failure_reopens():
    clock = FakeClock()
    breaker = make_breaker(threshold=1, timeout=30.0, clock=clock)
    await breaker.record_failure()
    clock.advance(31)
    assert await breaker.allow() is True
    await breaker.record_failure()
    assert await breaker.state() == CircuitState.OPEN
    assert await breaker.allow() is False  # timeout restarted
    clock.advance(31)
    assert await breaker.allow() is True  # recovers again later


async def test_half_open_limits_trial_requests():
    clock = FakeClock()
    breaker = make_breaker(threshold=1, timeout=30.0, trials=2, clock=clock)
    await breaker.record_failure()
    clock.advance(31)
    assert await breaker.allow() is True  # trial 1
    assert await breaker.allow() is True  # trial 2
    assert await breaker.allow() is False  # slots exhausted
    await breaker.record_success()
    assert await breaker.state() == CircuitState.HALF_OPEN  # 1 of 2 needed
    await breaker.record_success()
    assert await breaker.state() == CircuitState.CLOSED


async def test_snapshot_reports_state_and_config():
    breaker = make_breaker(threshold=2)
    await breaker.record_failure()
    snap = await breaker.snapshot()
    assert snap["state"] == "closed"
    assert snap["consecutive_failures"] == 1
    assert snap["failure_threshold"] == 2


# ─── Overrides & registry (Bab 55 closing rule) ───────────────────────────────

def test_parse_overrides():
    overrides = parse_overrides("openai:3/60/1, gemini:5/30/2")
    assert overrides["openai"] == BreakerConfig(3, 60.0, 1)
    assert overrides["gemini"] == BreakerConfig(5, 30.0, 2)
    assert parse_overrides("") == {}


def test_parse_overrides_rejects_malformed():
    with pytest.raises(ValueError):
        parse_overrides("openai=3/60/1")


def test_registry_applies_override_per_provider(monkeypatch):
    from api.config import settings

    monkeypatch.setattr(settings, "CIRCUIT_PROVIDER_OVERRIDES", "openai:2/10/1")
    monkeypatch.setattr(settings, "CIRCUIT_FAILURE_THRESHOLD", 7)
    registry = CircuitBreakerRegistry()
    assert registry.for_provider("openai").config.failure_threshold == 2
    assert registry.for_provider("claude").config.failure_threshold == 7
    # cached — same instance on second lookup
    assert registry.for_provider("openai") is registry.for_provider("openai")


# ─── Dispatcher integration (Bab 54 + 55) ─────────────────────────────────────

class StubAgent(BaseAgent):
    def __init__(self, role, output="ok", fail_times=0, provider="stub"):
        self.role = role
        self.agent_id = f"{role}-stub"
        self.default_provider = provider
        self._output = output
        self._fail_times = fail_times
        self.calls = 0

    async def execute(self, task: Task) -> AgentResult:
        self.calls += 1
        if self.calls <= self._fail_times:
            raise ProviderError("boom", provider=self.default_provider)
        return AgentResult(
            output=self._output,
            confidence=0.8,
            trace_id=task.trace_id,
            provider_used=self.default_provider,
            model_used="stub-m",
            role=self.role,
            agent_id=self.agent_id,
        )

    async def health_check(self) -> bool:
        return True


def make_dispatcher(agent, registry, **kwargs):
    reg = AgentRegistry()
    reg.register(agent)
    return Dispatcher(
        RoutingEngine(reg), max_retries=kwargs.pop("max_retries", 1), backoff_base=0, breakers=registry
    )


async def test_dispatcher_open_breaker_skips_primary(monkeypatch):
    """An Open breaker sends the task straight to the fallback provider."""
    primary = StubAgent("writer", output="primary", provider="openai")

    class FakeFallback(StubAgent):
        def __init__(self, role, prefer_fallback=False):
            super().__init__(role, output="fallback", provider="ollama")

    monkeypatch.setattr("orchestrator.dispatcher.GenericLLMAgent", FakeFallback)

    clock = FakeClock()
    registry = CircuitBreakerRegistry(clock=clock)
    registry._overrides = {"openai": BreakerConfig(failure_threshold=1, recovery_timeout=60.0)}
    await registry.for_provider("openai").record_failure()  # trip it

    disp = make_dispatcher(primary, registry)
    result = await disp.dispatch(Task(role="writer", prompt="p"))
    assert result.output == "fallback"
    assert primary.calls == 0  # provider never touched (Bab 55)


async def test_dispatcher_failures_trip_breaker(monkeypatch):
    """Consecutive dispatch failures accumulate in the breaker and open it."""
    failing = StubAgent("writer", fail_times=99, provider="openai")

    class FakeFallback(StubAgent):
        def __init__(self, role, prefer_fallback=False):
            super().__init__(role, output="fallback", provider="ollama")

    monkeypatch.setattr("orchestrator.dispatcher.GenericLLMAgent", FakeFallback)

    registry = CircuitBreakerRegistry(clock=FakeClock())
    registry._overrides = {"openai": BreakerConfig(failure_threshold=2, recovery_timeout=60.0)}

    disp = make_dispatcher(failing, registry, max_retries=1)  # 2 attempts = threshold
    result = await disp.dispatch(Task(role="writer", prompt="p"))
    assert result.output == "fallback"
    assert await registry.for_provider("openai").state() == CircuitState.OPEN

    # Second dispatch: breaker open — primary skipped entirely.
    calls_before = failing.calls
    result = await disp.dispatch(Task(role="writer", prompt="p"))
    assert result.output == "fallback"
    assert failing.calls == calls_before


async def test_dispatcher_open_fallback_breaker_fails_fast(monkeypatch):
    """Primary AND fallback breakers Open → fail fast without any provider call."""
    primary = StubAgent("writer", provider="openai")

    class FakeFallback(StubAgent):
        def __init__(self, role, prefer_fallback=False):
            super().__init__(role, output="fallback", provider="ollama")

    monkeypatch.setattr("orchestrator.dispatcher.GenericLLMAgent", FakeFallback)

    registry = CircuitBreakerRegistry(clock=FakeClock())
    registry._overrides = {
        "openai": BreakerConfig(failure_threshold=1, recovery_timeout=60.0),
        "ollama": BreakerConfig(failure_threshold=1, recovery_timeout=60.0),
    }
    await registry.for_provider("openai").record_failure()
    await registry.for_provider("ollama").record_failure()

    disp = make_dispatcher(primary, registry)
    result = await disp.dispatch(Task(role="writer", prompt="p"))
    assert not result.ok
    assert "circuit open" in result.error
    assert primary.calls == 0


async def test_dispatcher_success_closes_half_open_breaker(monkeypatch):
    """After recovery timeout a successful call closes the breaker again."""
    primary = StubAgent("writer", output="recovered", provider="openai")

    clock = FakeClock()
    registry = CircuitBreakerRegistry(clock=clock)
    registry._overrides = {"openai": BreakerConfig(failure_threshold=1, recovery_timeout=30.0)}
    await registry.for_provider("openai").record_failure()
    clock.advance(31)

    disp = make_dispatcher(primary, registry)
    result = await disp.dispatch(Task(role="writer", prompt="p"))
    assert result.output == "recovered"
    assert await registry.for_provider("openai").state() == CircuitState.CLOSED


async def test_dispatcher_breakers_disabled(monkeypatch):
    """breakers=None (ENABLE_CIRCUIT_BREAKER=false path) keeps old behaviour."""
    agent = StubAgent("writer", output="plain")
    reg = AgentRegistry()
    reg.register(agent)
    disp = Dispatcher(RoutingEngine(reg), max_retries=0, backoff_base=0)
    disp._breakers = None
    result = await disp.dispatch(Task(role="writer", prompt="p"))
    assert result.output == "plain"
