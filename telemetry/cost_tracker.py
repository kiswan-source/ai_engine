"""Cost Tracking (MASTER_INSTRUCTION.md Bab 27, 34, 56) — token cost per agent/provider/task/day.

Subscribes to ``agent.completed`` (Bab 23 prinsip 1) — Dispatcher enriches
that event with ``model``/``prompt_tokens``/``completion_tokens`` (Tahap 6)
precisely so this module needs no direct coupling to it.

Storage reuses :mod:`memory.stores`' ``ListStore`` (Tahap 3): every entry is
appended to one shared ledger scope, and the query methods load+filter it —
simple and consistent with the rest of the codebase's memory-tier pattern,
though it means those queries are O(ledger size); fine at the scale this
tool is meant for, not a high-throughput metrics pipeline.

``PRICING`` is a small editable table (Bab 56.1's task tiers, USD per 1K
tokens) — update it as vendors change rates; that's a data change, not an
architecture decision, so it doesn't need its own ADR.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass

from core.utils.logger import get_logger
from memory.stores import InMemoryListStore, ListStore, RedisListStore
from messaging import EventBus
from messaging.schemas import Event

logger = get_logger(__name__)

_LEDGER_SCOPE = "cost_ledger"
_LEDGER_MAX_ENTRIES = 100_000

# USD per 1K tokens: (prompt_price, completion_price). Approximate list prices;
# unknown models (including all Ollama/local models, Bab 56.1 "Ringan" tier)
# default to free — see _DEFAULT_PRICE.
PRICING: dict[tuple[str, str], tuple[float, float]] = {
    ("openai", "gpt-4o"): (0.0025, 0.010),
    ("openai", "gpt-4o-mini"): (0.00015, 0.0006),
    ("claude", "claude-sonnet-5"): (0.003, 0.015),
    ("gemini", "gemini-pro-latest"): (0.00125, 0.005),
    ("gemini", "gemini-2.5-flash"): (0.000075, 0.0003),
    ("gemini", "gemini-2.5-pro"): (0.00125, 0.005),
}
_DEFAULT_PRICE = (0.0, 0.0)


def price_for(provider: str, model: str) -> tuple[float, float]:
    return PRICING.get((provider, model), _DEFAULT_PRICE)


def estimate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    prompt_price, completion_price = price_for(provider, model)
    return (prompt_tokens / 1000) * prompt_price + (completion_tokens / 1000) * completion_price


@dataclass(frozen=True)
class CostEntry:
    """One priced ``agent.completed`` event."""

    trace_id: str
    task_id: str
    role: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    recorded_at: str


def _default_store() -> ListStore:
    from api.config import settings

    if settings.COST_BACKEND.lower() == "redis":
        return RedisListStore("cost")
    return InMemoryListStore()


class CostTracker:
    """Prices and accumulates cost per trace/day/provider/role from the Event Bus."""

    def __init__(self, event_bus: EventBus | None = None, store: ListStore | None = None) -> None:
        self._events = event_bus or EventBus()
        self._store = store or _default_store()
        self._started = False

    async def start(self) -> None:
        """Subscribe to the Event Bus. Idempotent — safe to call more than once."""
        if self._started:
            return
        await self._events.subscribe("agent.completed", self._on_agent_completed)
        self._started = True

    async def _on_agent_completed(self, event: Event) -> None:
        payload = event.payload
        provider = payload.get("provider", "unknown")
        model = payload.get("model", "unknown")
        prompt_tokens = payload.get("prompt_tokens", 0) or 0
        completion_tokens = payload.get("completion_tokens", 0) or 0
        cost = estimate_cost(provider, model, prompt_tokens, completion_tokens)
        entry = CostEntry(
            trace_id=event.trace_id,
            task_id=payload.get("task_id", ""),
            role=payload.get("role", "unknown"),
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            recorded_at=event.timestamp,
        )
        await self._store.append(_LEDGER_SCOPE, json.dumps(asdict(entry)), max_len=_LEDGER_MAX_ENTRIES)
        logger.info(
            "cost_tracker.record",
            trace_id=entry.trace_id,
            provider=provider,
            model=model,
            cost_usd=round(cost, 6),
        )

    async def _ledger(self) -> list[CostEntry]:
        raw = await self._store.last(_LEDGER_SCOPE, _LEDGER_MAX_ENTRIES)
        return [CostEntry(**json.loads(r)) for r in raw]

    async def cost_for_trace(self, trace_id: str) -> float:
        """Total cost recorded so far for one workflow trace (Bab 27 rule 4 budget check)."""
        return sum(e.cost_usd for e in await self._ledger() if e.trace_id == trace_id)

    async def cost_by_provider(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for e in await self._ledger():
            totals[e.provider] = totals.get(e.provider, 0.0) + e.cost_usd
        return totals

    async def cost_by_role(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for e in await self._ledger():
            totals[e.role] = totals.get(e.role, 0.0) + e.cost_usd
        return totals

    async def cost_for_day(self, day: dt.date | None = None) -> float:
        """Total cost recorded on ``day`` (default: today, UTC) — Bab 27/56 daily budget."""
        day = day or dt.datetime.now(dt.timezone.utc).date()
        return sum(
            e.cost_usd
            for e in await self._ledger()
            if dt.datetime.fromisoformat(e.recorded_at.replace("Z", "+00:00")).date() == day
        )

    async def total_cost(self) -> float:
        return sum(e.cost_usd for e in await self._ledger())
