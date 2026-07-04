"""Orchestrator — entry point that coordinates the multi-agent system (Bab 18).

Wires together the Planner (Bab 18), Routing Engine (Bab 53), Dispatcher +
Fallback (Bab 54), Workflow Engine (Bab 24) and Task Manager state machine
(Bab 49). It holds no domain-specific logic (Bab 18.1) and keeps state in the
Task Manager rather than process globals (Bab 18.2), so it stays horizontally
scalable.

Tahap 2 scope: sequential and parallel workflows. Reflection/Consensus/Human
Approval gates plug in at Tahap 4 without changing this contract.

Tahap 3: every workflow state transition is published on the Event Bus
(Bab 23 prinsip 1, roadmap exit criteria) and task state can persist to Redis
via ``TASK_STATE_BACKEND=redis``.
"""
from __future__ import annotations

from agents.base_agent import AgentResult, Task, new_id
from core.utils.logger import get_logger
from messaging import EventBus
from messaging.events import workflow_event
from registry.agent_registry import AgentRegistry, build_default_agent_registry
from workflows import WORKFLOWS, WorkflowResult

from .dispatcher import Dispatcher
from .planner import Planner
from .routing_engine import RoutingEngine
from .task_manager import State, TaskManager

logger = get_logger(__name__)


class Orchestrator:
    """Coordinates planning, routing, dispatch, and workflow execution."""

    def __init__(
        self,
        agent_registry: AgentRegistry | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.agents = agent_registry or build_default_agent_registry()
        self.events = event_bus or EventBus()
        self.routing = RoutingEngine(self.agents)
        self.dispatcher = Dispatcher(self.routing, event_bus=self.events)
        self.planner = Planner()
        self.tasks = TaskManager()

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
            mode: ``"sequential"`` or ``"parallel"`` (Bab 24).

        Returns:
            WorkflowResult: Aggregated result across all steps.

        Raises:
            ValueError: If ``mode`` is unsupported or ``roles`` is empty.
        """
        if mode not in WORKFLOWS:
            raise ValueError(f"unsupported workflow mode: {mode!r} (have: {list(WORKFLOWS)})")

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

        # Executing -> Completed / Failed
        if result.failed:
            await self._transition(trace_id, State.FAILED, error="one or more steps failed")
        else:
            await self._transition(trace_id, State.COMPLETED)

        logger.info(
            "orchestrator.done",
            trace_id=trace_id,
            state=self.tasks.state_of(trace_id).value if self.tasks.state_of(trace_id) else None,
            degraded=result.degraded,
            failed=result.failed,
        )
        return result

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
        task = Task(
            role=role,
            prompt=prompt,
            trace_id=trace_id or new_id(),
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return await self.dispatcher.dispatch(task)
