"""Circuit Breaker per provider (MASTER_INSTRUCTION.md Bab 55).

Protects the system from repeatedly calling a provider that is already down:
after ``failure_threshold`` consecutive failures the breaker trips to **Open**
and every new request is rejected without touching the provider, until
``recovery_timeout`` elapses; the breaker then moves to **Half-Open** and lets
``trial_requests`` probe calls through — all succeed → **Closed** (normal),
any fails → back to **Open** (Bab 55.2 state diagram).

State lives in a pluggable :class:`memory.stores.HashStore` (memory | redis via
``CIRCUIT_STATE_BACKEND``) — the same pattern every stateful piece has used
since Tahap 3, so multiple API replicas share one breaker view (Bab 38 rule 1).
Timestamps are wall-clock (``time.time``) for exactly that reason: monotonic
clocks aren't comparable across processes.

Per Bab 55's closing rule, parameters must be tunable per provider, not one
global constant: ``CIRCUIT_PROVIDER_OVERRIDES`` accepts
``"openai:3/60/1,gemini:5/30/2"`` (``threshold/recovery_seconds/trials``);
providers without an override use the ``CIRCUIT_*`` defaults.

State transitions are published on the Event Bus (``circuit.opened`` /
``circuit.half_open`` / ``circuit.closed``) best-effort, mirroring how the
Dispatcher publishes agent lifecycle events — telemetry observes, nothing
couples to it (Bab 23 prinsip 1).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from core.utils.logger import get_logger

logger = get_logger(__name__)

_STORE_PREFIX = "circuit"


class CircuitState(str, Enum):
    """Bab 55.1 — the three breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class BreakerConfig:
    """Bab 55.3 key parameters for one provider's breaker."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    trial_requests: int = 1


def parse_overrides(raw: str) -> dict[str, BreakerConfig]:
    """Parse ``CIRCUIT_PROVIDER_OVERRIDES`` (``"name:threshold/timeout/trials,…"``).

    Args:
        raw: The raw env value; blank yields no overrides.

    Returns:
        Mapping of provider name to its :class:`BreakerConfig`.

    Raises:
        ValueError: If an entry is malformed — a silently ignored typo here
            would leave a provider on defaults without anyone noticing (Bab 10.2).
    """
    overrides: dict[str, BreakerConfig] = {}
    for entry in filter(None, (e.strip() for e in raw.split(","))):
        try:
            name, params = entry.split(":")
            threshold, timeout, trials = params.split("/")
            overrides[name.strip()] = BreakerConfig(
                failure_threshold=int(threshold),
                recovery_timeout=float(timeout),
                trial_requests=int(trials),
            )
        except ValueError as exc:
            raise ValueError(
                f"invalid CIRCUIT_PROVIDER_OVERRIDES entry {entry!r} "
                "(expected 'provider:threshold/recovery_seconds/trials')"
            ) from exc
    return overrides


class CircuitBreaker:
    """One provider's breaker state machine (Bab 55.2) over a shared store."""

    def __init__(
        self,
        provider: str,
        config: BreakerConfig,
        store=None,
        event_bus=None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        from memory.stores import InMemoryHashStore

        self.provider = provider
        self.config = config
        self._store = store or InMemoryHashStore()
        self._events = event_bus
        self._clock = clock

    # ── persistence ──────────────────────────────────────────────────────────

    async def _load(self) -> dict[str, str]:
        raw = await self._store.get_all(self.provider)
        # Redis returns bytes keys/values; normalise once here.
        return {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in raw.items()
        }

    async def _save(self, **fields: object) -> None:
        for field, value in fields.items():
            await self._store.set_field(self.provider, field, str(value))

    async def _emit(self, event_type: str, trace_id: str | None, **payload) -> None:
        if self._events is None:
            return
        await self._events.emit(
            event_type,
            source=f"circuit:{self.provider}",
            trace_id=trace_id or "-",
            payload={"provider": self.provider, **payload},
        )

    # ── state machine (Bab 55.2) ─────────────────────────────────────────────

    async def state(self) -> CircuitState:
        """Current state (without side effects — ``allow()`` drives transitions)."""
        data = await self._load()
        return CircuitState(data.get("state", CircuitState.CLOSED.value))

    async def allow(self, trace_id: str | None = None) -> bool:
        """Whether a request may go to the provider right now.

        Open → Half-Open happens here once ``recovery_timeout`` has elapsed;
        Half-Open admits at most ``trial_requests`` probes (Bab 55.3).
        """
        from messaging import events as ev

        data = await self._load()
        state = data.get("state", CircuitState.CLOSED.value)

        if state == CircuitState.CLOSED.value:
            return True

        if state == CircuitState.OPEN.value:
            opened_at = float(data.get("opened_at", 0.0))
            if self._clock() - opened_at < self.config.recovery_timeout:
                return False
            # Recovery timeout reached — admit this request as the first trial.
            await self._save(state=CircuitState.HALF_OPEN.value, trials=1, trial_successes=0)
            logger.info("circuit.half_open", provider=self.provider)
            await self._emit(ev.CIRCUIT_HALF_OPEN, trace_id)
            return True

        # HALF_OPEN — admit while trial slots remain.
        trials = int(data.get("trials", 0))
        if trials < self.config.trial_requests:
            await self._save(trials=trials + 1)
            return True
        return False

    async def record_success(self, trace_id: str | None = None) -> None:
        """Report a successful provider call (closes the breaker after trials)."""
        from messaging import events as ev

        data = await self._load()
        state = data.get("state", CircuitState.CLOSED.value)

        if state == CircuitState.HALF_OPEN.value:
            successes = int(data.get("trial_successes", 0)) + 1
            if successes >= self.config.trial_requests:
                await self._store.delete(self.provider)  # full reset = Closed
                logger.info("circuit.closed", provider=self.provider)
                await self._emit(ev.CIRCUIT_CLOSED, trace_id)
            else:
                await self._save(trial_successes=successes)
        elif int(data.get("failures", 0)):
            await self._save(failures=0)  # a success breaks the consecutive-failure run

    async def record_failure(self, trace_id: str | None = None) -> None:
        """Report a failed provider call (may trip the breaker to Open)."""
        from messaging import events as ev

        data = await self._load()
        state = data.get("state", CircuitState.CLOSED.value)
        now = self._clock()

        if state == CircuitState.HALF_OPEN.value:
            # A failed trial re-opens immediately (Bab 55.2).
            await self._save(state=CircuitState.OPEN.value, opened_at=now, failures=0)
            logger.warning("circuit.reopened", provider=self.provider)
            await self._emit(ev.CIRCUIT_OPENED, trace_id, reason="trial_failed")
            return

        failures = int(data.get("failures", 0)) + 1
        if state == CircuitState.CLOSED.value and failures >= self.config.failure_threshold:
            await self._save(state=CircuitState.OPEN.value, opened_at=now, failures=failures)
            logger.warning("circuit.opened", provider=self.provider, failures=failures)
            await self._emit(ev.CIRCUIT_OPENED, trace_id, failures=failures)
        else:
            # CLOSED below threshold, or a straggler failing while already OPEN
            # (its request departed before the trip) — keep counting/stay put.
            await self._save(failures=failures)

    async def snapshot(self) -> dict:
        """Dashboard view: state + counters + config (Bab 62 Provider Dashboard)."""
        data = await self._load()
        return {
            "state": data.get("state", CircuitState.CLOSED.value),
            "consecutive_failures": int(data.get("failures", 0)),
            "failure_threshold": self.config.failure_threshold,
            "recovery_timeout_s": self.config.recovery_timeout,
            "trial_requests": self.config.trial_requests,
        }


class CircuitBreakerRegistry:
    """Lazily builds and caches one :class:`CircuitBreaker` per provider."""

    def __init__(self, store=None, event_bus=None, clock: Callable[[], float] = time.time) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._store = store
        self._events = event_bus
        self._clock = clock
        self._overrides: dict[str, BreakerConfig] | None = None

    def _build_store(self):
        if self._store is not None:
            return self._store
        from api.config import settings
        from memory.stores import InMemoryHashStore, RedisHashStore

        if settings.CIRCUIT_STATE_BACKEND == "redis":
            self._store = RedisHashStore(_STORE_PREFIX)
        else:
            self._store = InMemoryHashStore()
        return self._store

    def _build_events(self):
        if self._events is None:
            from messaging import EventBus

            # The broker underneath is a process-wide singleton, so a fresh
            # EventBus here publishes to the same subscribers (Tracer etc.)
            # as the Dispatcher's own bus.
            self._events = EventBus()
        return self._events

    def _config_for(self, provider: str) -> BreakerConfig:
        from api.config import settings

        if self._overrides is None:
            self._overrides = parse_overrides(settings.CIRCUIT_PROVIDER_OVERRIDES)
        return self._overrides.get(
            provider,
            BreakerConfig(
                failure_threshold=settings.CIRCUIT_FAILURE_THRESHOLD,
                recovery_timeout=settings.CIRCUIT_RECOVERY_TIMEOUT,
                trial_requests=settings.CIRCUIT_TRIAL_REQUESTS,
            ),
        )

    def for_provider(self, provider: str) -> CircuitBreaker:
        """The breaker guarding ``provider`` (created on first use)."""
        if provider not in self._breakers:
            self._breakers[provider] = CircuitBreaker(
                provider,
                self._config_for(provider),
                store=self._build_store(),
                event_bus=self._build_events(),
                clock=self._clock,
            )
        return self._breakers[provider]

    async def snapshot(self) -> dict[str, dict]:
        """All known breakers' states, keyed by provider (for the dashboard)."""
        return {name: await breaker.snapshot() for name, breaker in sorted(self._breakers.items())}


# Shared default registry — the Dispatcher and Provider Dashboard read the same
# instance so "what the dispatcher skips" and "what the dashboard shows" can't
# drift apart (Bab 62's one-source-of-truth rule). Tests inject their own.
breakers = CircuitBreakerRegistry()
