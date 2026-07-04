"""Orchestrator — entry point that coordinates the multi-agent system (Bab 18).

Wires together the Planner (Bab 18), Routing Engine (Bab 53), Dispatcher +
Fallback (Bab 54), Workflow Engine (Bab 24) and Task Manager state machine
(Bab 49). It holds no domain-specific logic (Bab 18.1) and keeps state in the
Task Manager rather than process globals (Bab 18.2), so it stays horizontally
scalable.

Tahap 3: every workflow state transition is published on the Event Bus
(Bab 23 prinsip 1, roadmap exit criteria) and task state can persist to Redis
via ``TASK_STATE_BACKEND=redis``.

Tahap 4: Reflection/Voting/Consensus workflows report ``WorkflowResult.escalate``
when their confidence/agreement never cleared the Bab 28 threshold. When that
happens (and ``ENABLE_HUMAN_APPROVAL`` is on), ``run()`` stops at
``State.REVIEWING`` and opens a Human Approval request (Bab 61) instead of
auto-completing — call :meth:`finalize_approval` once a human decides.

Tahap 6: ``self.costs``/``self.metrics``/``self.tracer`` (``telemetry.*``)
subscribe to this orchestrator's own Event Bus on first ``run()``/``run_single()``
call — zero coupling, they only observe events Dispatcher/``_transition``
already publish. If a task's running cost exceeds ``COST_BUDGET_PER_TASK``,
``run()`` escalates to Human Approval the same way a low-confidence result
does (Bab 61.2 — cost over budget requires approval too), reason
``"cost_budget_exceeded"``.

Note: ``workflows`` imports back into this package (every workflow pattern
takes a ``Dispatcher``), so the ``workflows`` names actually used at runtime
here are imported lazily inside methods rather than at module level — that's
what lets either package be the first one imported without tripping a partial-
init ``ImportError``, matching the lazy-import seam already used in
``registry.agent_registry.build_default_agent_registry`` and
``task_manager._default_store``. ``telemetry`` has no such cycle (it never
imports ``orchestrator``/``workflows``), so it's imported normally at module
level.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from agents.base_agent import AgentResult, Task, new_id
from api.config import settings
from core.utils.logger import get_logger
from messaging import EventBus
from messaging.events import workflow_event
from registry.agent_registry import AgentRegistry, build_default_agent_registry
from telemetry.cost_tracker import CostTracker
from telemetry.metrics import MetricsCollector
from telemetry.tracing import Tracer

from .dispatcher import Dispatcher
from .planner import Planner
from .routing_engine import RoutingEngine
from .task_manager import State, TaskManager

if TYPE_CHECKING:
    from workflows import WorkflowResult
    from workflows.approval import ApprovalRequest, HumanApprovalGate

logger = get_logger(__name__)


class Orchestrator:
    """Coordinates planning, routing, dispatch, and workflow execution."""

    def __init__(
        self,
        agent_registry: AgentRegistry | None = None,
        event_bus: EventBus | None = None,
        approval_gate: "HumanApprovalGate | None" = None,
        cost_tracker: CostTracker | None = None,
        metrics: MetricsCollector | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        from workflows.approval import HumanApprovalGate  # lazy: see module docstring

        self.agents = agent_registry or build_default_agent_registry()
        self.events = event_bus or EventBus()
        self.routing = RoutingEngine(self.agents)
        self.dispatcher = Dispatcher(self.routing, event_bus=self.events)
        self.planner = Planner()
        self.tasks = TaskManager()
        self.approval = approval_gate or HumanApprovalGate(event_bus=self.events)
        self.costs = cost_tracker or CostTracker(event_bus=self.events)
        self.metrics = metrics or MetricsCollector(event_bus=self.events)
        self.tracer = tracer or Tracer(event_bus=self.events)
        self._telemetry_started = False

    async def _ensure_telemetry_started(self) -> None:
        """Subscribe cost/metrics/tracing to this orchestrator's Event Bus (idempotent).

        Deferred out of ``__init__`` because ``EventBus.subscribe`` is a
        coroutine and ``__init__`` can't be async.
        """
        if self._telemetry_started:
            return
        await self.costs.start()
        await self.metrics.start()
        await self.tracer.start()
        self._telemetry_started = True

    async def _transition(self, trace_id: str, dst: State, error: str | None = None) -> None:
        """Move the workflow state and publish the matching event (Bab 23 prinsip 1)."""
        self.tasks.transition(trace_id, dst, error=error)
        payload = {"error": error} if error else {}
        await self.events.emit(
            workflow_event(dst.value), source="orchestrator", trace_id=trace_id, payload=payload
        )

    async def run(
        self,
        prompt: str,
        roles: list[str],
        mode: str = "sequential",
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        trace_id: str | None = None,
    ) -> WorkflowResult:
        """Plan and execute a multi-agent workflow for ``prompt``.

        Args:
            roles: Ordered agent roles to involve.
            mode: A key of ``workflows.WORKFLOWS`` — ``"sequential"``,
                ``"parallel"``, ``"reflection"``, ``"voting"``, or
                ``"consensus"`` (Bab 24).

        Returns:
            WorkflowResult: Aggregated result across all steps.

        Raises:
            ValueError: If ``mode`` is unsupported or ``roles`` is empty.
        """
        from workflows import WORKFLOWS  # lazy: see module docstring

        if mode not in WORKFLOWS:
            raise ValueError(f"unsupported workflow mode: {mode!r} (have: {list(WORKFLOWS)})")
        if mode in ("voting", "consensus") and not settings.ENABLE_CONSENSUS_VOTING:
            raise ValueError(f"mode {mode!r} is disabled (ENABLE_CONSENSUS_VOTING=false, Bab 57)")

        await self._ensure_telemetry_started()
        trace_id = trace_id or new_id()
        self.tasks.track(trace_id, State.PENDING)
        await self.events.emit(
            workflow_event(State.PENDING.value),
            source="orchestrator",
            trace_id=trace_id,
            payload={"mode": mode, "roles": roles},
        )
        logger.info("orchestrator.run", trace_id=trace_id, mode=mode, roles=roles)

        # Pending -> Planning
        await self._transition(trace_id, State.PLANNING)
        plan = self.planner.plan(
            prompt=prompt,
            roles=roles,
            mode=mode,
            trace_id=trace_id,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Planning -> Executing
        await self._transition(trace_id, State.EXECUTING)
        workflow = WORKFLOWS[mode]()
        result = await workflow.run(plan.graph, self.dispatcher)

        # Cost Optimization (Bab 27 rule 4, Bab 61.2): a task over budget needs
        # Human Approval exactly like a low-confidence result does.
        #
        # Correctness note: this reads cost_tracker's ledger immediately after
        # workflow.run() returns, which is only guaranteed to include every
        # dispatch's cost when event delivery is synchronous — true today
        # (MESSAGE_BROKER=memory delivers subscribers inline, Bab 23). If a
        # deployment switches to MESSAGE_BROKER=redis, RedisBroker delivers via
        # a background reader task (see messaging/broker.py), so this check
        # could race against the last agent.completed event still in flight
        # and under-count the task's true cost. Not hit in this single-process
        # deployment; worth revisiting before running multi-process with a
        # Redis message broker.
        task_cost = await self.costs.cost_for_trace(trace_id)
        over_budget = task_cost > settings.COST_BUDGET_PER_TASK

        # Executing -> Reviewing (needs a human, Bab 61) / Completed / Failed
        if (result.escalate or over_budget) and settings.ENABLE_HUMAN_APPROVAL:
            await self._transition(trace_id, State.REVIEWING)
            if over_budget:
                reason = "cost_budget_exceeded"
            elif mode == "reflection":
                reason = "reflection_exhausted"
            else:
                reason = "low_confidence"
            await self.approval.request(trace_id, reason=reason)
            logger.info("orchestrator.pending_approval", trace_id=trace_id, reason=reason)
        elif result.failed:
            await self._transition(trace_id, State.FAILED, error="one or more steps failed")
        else:
            await self._transition(trace_id, State.COMPLETED)

        logger.info(
            "orchestrator.done",
            trace_id=trace_id,
            state=self.tasks.state_of(trace_id).value if self.tasks.state_of(trace_id) else None,
            degraded=result.degraded,
            failed=result.failed,
            escalate=result.escalate,
            cost_usd=round(task_cost, 6),
            over_budget=over_budget,
        )
        return result

    async def finalize_approval(
        self, trace_id: str, approved: bool, decided_by: str, reason: str = ""
    ) -> State:
        """Resolve a pending Human Approval request (Bab 61) and settle the task.

        Raises:
            KeyError: If ``trace_id`` has no pending approval request.
        """
        await self.approval.decide(trace_id, approved=approved, decided_by=decided_by, reason=reason)
        if approved:
            await self._transition(trace_id, State.APPROVED)
            await self._transition(trace_id, State.COMPLETED)
        else:
            await self._transition(trace_id, State.CANCELLED)
        return self.tasks.state_of(trace_id)

    def pending_approvals(self) -> list[ApprovalRequest]:
        """Approval requests still awaiting a human decision (Bab 61.3)."""
        return self.approval.pending()

    async def run_single(
        self,
        prompt: str,
        role: str,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        trace_id: str | None = None,
    ) -> AgentResult:
        """Dispatch a single task to one agent (no workflow overhead)."""
        await self._ensure_telemetry_started()
        task = Task(
            role=role,
            prompt=prompt,
            trace_id=trace_id or new_id(),
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return await self.dispatcher.dispatch(task)
