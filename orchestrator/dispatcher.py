"""Dispatcher — sends a task to its agent and applies the Fallback Strategy.

Implements the tiered Fallback Strategy (MASTER_INSTRUCTION.md Bab 54):

    1. Retry           — same agent/provider with exponential backoff (Bab 9).
    2. Switch Provider — a fallback agent (local Ollama per Model Registry, Bab 20).
    3. Graceful Degrade — fallback result is flagged ``degraded=True`` (Bab 54.3).
    4. (Escalation / Circuit Breaker land in Tahap 4 / dedicated modules.)

A single agent failure never crashes the workflow: exhausted fallbacks yield an
``AgentResult`` with ``error`` set, not an exception (Bab 10.4).

Tahap 3: agent lifecycle transitions (Bab 48) are published on the Event Bus —
``agent.assigned`` → ``agent.running`` → ``agent.completed`` /
``agent.retry`` / ``agent.failed`` — best-effort, per Bab 23 prinsip 1.

Tahap 6: ``agent.completed`` carries ``model``/``prompt_tokens``/
``completion_tokens``/``confidence`` in its payload so ``telemetry.cost_tracker``
and ``telemetry.metrics`` can observe cost and latency purely by subscribing to
the Event Bus — no direct coupling from this module to either.
"""
from __future__ import annotations

import asyncio

from agents.base_agent import AgentResult, Task
from agents.generic_agent import GenericLLMAgent
from api.config import settings
from core.utils.logger import get_logger
from messaging import EventBus
from messaging import events as ev
from providers.exceptions import ProviderError

from .routing_engine import RoutingEngine, RoutingError

logger = get_logger(__name__)


class Dispatcher:
    """Routes a task to an agent and executes it with retry + fallback."""

    def __init__(
        self,
        routing_engine: RoutingEngine,
        max_retries: int | None = None,
        backoff_base: float | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._routing = routing_engine
        self._max_retries = settings.PROVIDER_MAX_RETRIES if max_retries is None else max_retries
        self._backoff = settings.PROVIDER_RETRY_BACKOFF if backoff_base is None else backoff_base
        self._events = event_bus or EventBus()

    async def _emit(self, event_type: str, task: Task, agent_id: str, **payload) -> None:
        await self._events.emit(
            event_type,
            source=agent_id,
            trace_id=task.trace_id,
            payload={"task_id": task.task_id, "role": task.role, **payload},
        )

    async def dispatch(self, task: Task) -> AgentResult:
        """Execute ``task``, applying retry then provider fallback on failure."""
        try:
            agent = self._routing.route(task)
        except RoutingError as exc:
            logger.error("dispatch.no_route", trace_id=task.trace_id, error=str(exc))
            await self._emit(ev.AGENT_FAILED, task, "dispatcher", error=str(exc))
            return self._failed(task, f"routing failed: {exc}")

        await self._emit(ev.AGENT_ASSIGNED, task, agent.agent_id)

        # Tier 1: retry on the primary agent/provider.
        last_error: str | None = None
        for attempt in range(self._max_retries + 1):
            try:
                await self._emit(ev.AGENT_RUNNING, task, agent.agent_id, attempt=attempt)
                result = await agent.execute(task)
                await self._emit(
                    ev.AGENT_COMPLETED,
                    task,
                    agent.agent_id,
                    provider=result.provider_used,
                    model=result.model_used,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    confidence=result.confidence,
                )
                return result
            except ProviderError as exc:
                last_error = str(exc)
                logger.warning(
                    "dispatch.retry",
                    trace_id=task.trace_id,
                    agent_id=agent.agent_id,
                    attempt=attempt,
                    error=last_error,
                )
                if attempt < self._max_retries:
                    await self._emit(ev.AGENT_RETRY, task, agent.agent_id, attempt=attempt)
                    await asyncio.sleep(self._backoff * (2 ** attempt))

        # Tier 2/3: switch to the role's fallback provider and degrade gracefully.
        logger.warning("dispatch.switch_provider", trace_id=task.trace_id, role=agent.role)
        await self._emit(ev.AGENT_RETRY, task, agent.agent_id, tier="switch_provider")
        try:
            fallback_agent = GenericLLMAgent(agent.role, prefer_fallback=True)
            await self._emit(ev.AGENT_RUNNING, task, fallback_agent.agent_id, fallback=True)
            result = await fallback_agent.execute(task)
            # execute() already stamps degraded=True for a fallback agent.
            await self._emit(
                ev.AGENT_COMPLETED,
                task,
                fallback_agent.agent_id,
                provider=result.provider_used,
                model=result.model_used,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                confidence=result.confidence,
                degraded=True,
            )
            return result
        except ProviderError as exc:
            logger.error("dispatch.fallback_failed", trace_id=task.trace_id, error=str(exc))
            await self._emit(
                ev.AGENT_FAILED, task, agent.agent_id, error=f"{last_error} | {exc}"
            )
            return self._failed(task, f"primary+fallback failed: {last_error} | {exc}")

    @staticmethod
    def _failed(task: Task, message: str) -> AgentResult:
        return AgentResult(
            output="",
            confidence=0.0,
            trace_id=task.trace_id,
            provider_used="none",
            model_used="none",
            role=task.role,
            degraded=True,
            error=message,
        )
