"""Unit tests for the orchestrator + workflow layer (Bab 18, 24, 49, 53, 54).

Agents are stubbed — no provider/network calls (Bab 12.3).
"""
import pytest

from agents.base_agent import AgentResult, BaseAgent, Task
from orchestrator import Orchestrator, State
from orchestrator.dispatcher import Dispatcher
from orchestrator.execution_graph import ExecutionGraph, GraphValidationError, Step
from orchestrator.planner import Planner
from orchestrator.routing_engine import RoutingEngine, RoutingError
from orchestrator.task_manager import IllegalTransitionError, TaskManager
from providers.exceptions import ProviderError
from registry.agent_registry import AgentRegistry
from workflows.parallel import ParallelWorkflow
from workflows.sequential import SequentialWorkflow


# ─── Test doubles ─────────────────────────────────────────────────────────────

class StubAgent(BaseAgent):
    def __init__(self, role, output="ok", fail_times=0, provider="stub"):
        self.role = role
        self.agent_id = f"{role}-stub"
        self.default_provider = provider
        self._output = output
        self._fail_times = fail_times
        self._provider = provider
        self.calls = 0
        self.last_prompt = ""

    async def execute(self, task: Task) -> AgentResult:
        self.calls += 1
        self.last_prompt = task.prompt
        if self.calls <= self._fail_times:
            raise ProviderError("boom", provider=self._provider)
        return AgentResult(
            output=self._output,
            confidence=0.8,
            trace_id=task.trace_id,
            provider_used=self._provider,
            model_used="stub-m",
            role=self.role,
            agent_id=self.agent_id,
        )

    async def health_check(self) -> bool:
        return True


def registry_with(*agents) -> AgentRegistry:
    reg = AgentRegistry()
    for a in agents:
        reg.register(a)
    return reg


# ─── Task Manager / State Machine (Bab 49) ────────────────────────────────────

def test_valid_transition_path():
    tm = TaskManager()
    tm.track("w1")
    for state in (State.PLANNING, State.EXECUTING, State.COMPLETED):
        tm.transition("w1", state)
    assert tm.state_of("w1") == State.COMPLETED
    assert tm.get("w1").is_terminal


def test_illegal_transition_raises():
    tm = TaskManager()
    tm.track("w1")
    with pytest.raises(IllegalTransitionError):
        tm.transition("w1", State.COMPLETED)  # pending -> completed not allowed


def test_transition_to_same_state_is_noop():
    tm = TaskManager()
    tm.track("w1")
    tm.transition("w1", State.PENDING)
    assert tm.state_of("w1") == State.PENDING


# ─── Execution Graph (Bab 18) ─────────────────────────────────────────────────

def _step(sid, role="writer", deps=()):
    return Step(step_id=sid, task=Task(role=role, prompt="p", trace_id="t"), depends_on=deps)


def test_graph_topological_layers():
    g = ExecutionGraph()
    g.add_step(_step("a"))
    g.add_step(_step("b", deps=("a",)))
    g.add_step(_step("c", deps=("a",)))
    g.add_step(_step("d", deps=("b", "c")))
    layers = g.topological_layers()
    assert [sorted(s.step_id for s in layer) for layer in layers] == [["a"], ["b", "c"], ["d"]]


def test_graph_cycle_detected():
    g = ExecutionGraph()
    g.add_step(_step("a", deps=("b",)))
    g.add_step(_step("b", deps=("a",)))
    with pytest.raises(GraphValidationError):
        g.topological_layers()


def test_graph_missing_dependency():
    g = ExecutionGraph()
    g.add_step(_step("a", deps=("ghost",)))
    with pytest.raises(GraphValidationError):
        g.validate()


# ─── Planner (Bab 18) ─────────────────────────────────────────────────────────

def test_planner_sequential_chains_dependencies():
    plan = Planner().plan("do it", ["planner", "writer"], mode="sequential")
    order = plan.graph.linear_order()
    assert [s.task.role for s in order] == ["planner", "writer"]
    assert order[1].depends_on == (order[0].step_id,)


def test_planner_parallel_has_no_dependencies():
    plan = Planner().plan("do it", ["research", "analyst"], mode="parallel")
    assert all(s.depends_on == () for s in plan.graph.steps.values())


def test_planner_rejects_empty_roles():
    with pytest.raises(ValueError):
        Planner().plan("x", [], mode="sequential")


# ─── Routing Engine (Bab 53) ──────────────────────────────────────────────────

def test_routing_uses_explicit_role():
    reg = registry_with(StubAgent("analyst"))
    engine = RoutingEngine(reg)
    agent = engine.route(Task(role="analyst", prompt="p"))
    assert agent.role == "analyst"


def test_routing_infers_role_from_task_type():
    reg = registry_with(StubAgent("vision"))
    engine = RoutingEngine(reg)
    task = Task(role="", prompt="p", metadata={"task_type": "pdf"})
    assert engine.infer_role(task) == "vision"


def test_routing_no_agent_raises():
    engine = RoutingEngine(AgentRegistry())
    with pytest.raises(RoutingError):
        engine.route(Task(role="analyst", prompt="p"))


# ─── Dispatcher + Fallback (Bab 54) ───────────────────────────────────────────

async def test_dispatch_success():
    agent = StubAgent("writer", output="hello")
    disp = Dispatcher(RoutingEngine(registry_with(agent)), max_retries=1, backoff_base=0)
    result = await disp.dispatch(Task(role="writer", prompt="p"))
    assert result.output == "hello"
    assert result.ok


async def test_dispatch_retries_then_succeeds():
    agent = StubAgent("writer", output="recovered", fail_times=1)
    disp = Dispatcher(RoutingEngine(registry_with(agent)), max_retries=2, backoff_base=0)
    result = await disp.dispatch(Task(role="writer", prompt="p"))
    assert result.output == "recovered"
    assert agent.calls == 2  # failed once, succeeded on retry


async def test_dispatch_switches_to_fallback(monkeypatch):
    always_fail = StubAgent("writer", fail_times=99)

    class FakeFallbackAgent(StubAgent):
        def __init__(self, role, prefer_fallback=False):
            super().__init__(role, output="fallback-output")

        async def execute(self, task):
            r = await super().execute(task)
            # a fallback agent stamps degraded=True
            return AgentResult(**{**r.__dict__, "degraded": True})

    monkeypatch.setattr("orchestrator.dispatcher.GenericLLMAgent", FakeFallbackAgent)
    disp = Dispatcher(RoutingEngine(registry_with(always_fail)), max_retries=1, backoff_base=0)
    result = await disp.dispatch(Task(role="writer", prompt="p"))
    assert result.output == "fallback-output"
    assert result.degraded is True


async def test_dispatch_no_route_returns_error_result():
    disp = Dispatcher(RoutingEngine(AgentRegistry()), max_retries=0, backoff_base=0)
    result = await disp.dispatch(Task(role="writer", prompt="p"))
    assert not result.ok
    assert "routing failed" in result.error


# ─── Workflows (Bab 24) ───────────────────────────────────────────────────────

async def test_sequential_chains_output_into_next_prompt():
    a1 = StubAgent("planner", output="PLAN-A")
    a2 = StubAgent("writer", output="FINAL")
    disp = Dispatcher(RoutingEngine(registry_with(a1, a2)), max_retries=0, backoff_base=0)
    plan = Planner().plan("base prompt", ["planner", "writer"], mode="sequential")
    result = await SequentialWorkflow().run(plan.graph, disp)
    assert result.final_output == "FINAL"
    assert "PLAN-A" in a2.last_prompt  # writer saw planner's output
    assert not result.failed


async def test_parallel_runs_all_and_isolates_failure(monkeypatch):
    good = StubAgent("research", output="R")
    bad = StubAgent("analyst", fail_times=99)
    disp = Dispatcher(RoutingEngine(registry_with(good, bad)), max_retries=0, backoff_base=0)
    plan = Planner().plan("p", ["research", "analyst"], mode="parallel")

    # Force the bad agent's fallback to also fail so we observe an error result,
    # not a silent local recovery. monkeypatch auto-restores after the test.
    class FailingFallback(StubAgent):
        def __init__(self, role, prefer_fallback=False):
            super().__init__(role, fail_times=99)

    monkeypatch.setattr("orchestrator.dispatcher.GenericLLMAgent", FailingFallback)
    result = await ParallelWorkflow().run(plan.graph, disp)

    assert result.failed  # analyst branch failed
    assert any(r.output == "R" for r in result.results)  # research still succeeded


# ─── Orchestrator end-to-end (Bab 18) ─────────────────────────────────────────

async def test_orchestrator_run_sequential_completes():
    reg = registry_with(StubAgent("analyst", output="A"), StubAgent("writer", output="W"))
    orch = Orchestrator(agent_registry=reg)
    result = await orch.run("hello", ["analyst", "writer"], mode="sequential")
    assert result.final_output == "W"
    assert orch.tasks.state_of(result.trace_id) == State.COMPLETED


async def test_orchestrator_run_marks_failed(monkeypatch):
    reg = registry_with(StubAgent("writer", fail_times=99))

    # Fallback also fails -> workflow failed -> state FAILED.
    import orchestrator.dispatcher as dmod

    class FailingFallback(StubAgent):
        def __init__(self, role, prefer_fallback=False):
            super().__init__(role, fail_times=99)

    monkeypatch.setattr(dmod, "GenericLLMAgent", FailingFallback)
    orch = Orchestrator(agent_registry=reg)
    orch.dispatcher = Dispatcher(orch.routing, max_retries=0, backoff_base=0)
    result = await orch.run("x", ["writer"], mode="sequential")
    assert result.failed
    assert orch.tasks.state_of(result.trace_id) == State.FAILED


async def test_orchestrator_rejects_unknown_mode():
    orch = Orchestrator(agent_registry=registry_with(StubAgent("writer")))
    with pytest.raises(ValueError):
        await orch.run("x", ["writer"], mode="telepathy")


# ─── Tahap 3: Redis-backed task state (Bab 49, kontrak tak berubah) ──────────

class FakeSyncRedis:
    """Minimal sync stand-in for redis.Redis (get/setex)."""

    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, ttl, value):
        self.data[key] = value


def test_redis_task_store_persists_across_managers():
    from orchestrator.task_manager import RedisTaskStore

    fake = FakeSyncRedis()
    tm1 = TaskManager(store=RedisTaskStore(client=fake, ttl=60))
    tm1.track("w1")
    tm1.transition("w1", State.PLANNING)
    tm1.transition("w1", State.EXECUTING)

    # "Restart": a new manager over the same Redis sees the same state+history.
    tm2 = TaskManager(store=RedisTaskStore(client=fake, ttl=60))
    assert tm2.state_of("w1") == State.EXECUTING
    assert [s for s, _ in tm2.get("w1").history] == [
        State.PENDING, State.PLANNING, State.EXECUTING,
    ]
    with pytest.raises(IllegalTransitionError):
        tm2.transition("w1", State.APPROVED)  # rules still enforced from Redis


# ─── Tahap 3: Event Bus lifecycle publishing (Bab 23 prinsip 1, Bab 48/49) ───

async def test_orchestrator_publishes_workflow_and_agent_lifecycle_events():
    from messaging import EventBus, InMemoryBroker

    bus = EventBus(InMemoryBroker())
    seen = []

    async def collect(event):
        seen.append(event)

    await bus.subscribe("workflow.*", collect)
    await bus.subscribe("agent.*", collect)

    reg = registry_with(StubAgent("writer", output="W"))
    orch = Orchestrator(agent_registry=reg, event_bus=bus)
    result = await orch.run("halo", ["writer"], mode="sequential")

    types = [e.event_type for e in seen]
    assert types == [
        "workflow.pending",
        "workflow.planning",
        "workflow.executing",
        "agent.assigned",
        "agent.running",
        "agent.completed",
        "workflow.completed",
    ]
    # Every event carries the workflow's trace_id (Bab 11 — correlation).
    assert all(e.trace_id == result.trace_id for e in seen)


async def test_failed_dispatch_publishes_agent_failed(monkeypatch):
    from messaging import EventBus, InMemoryBroker

    bus = EventBus(InMemoryBroker())
    seen = []

    async def collect(event):
        seen.append(event.event_type)

    await bus.subscribe("agent.*", collect)

    class FailingFallback(StubAgent):
        def __init__(self, role, prefer_fallback=False):
            super().__init__(role, fail_times=99)

    monkeypatch.setattr("orchestrator.dispatcher.GenericLLMAgent", FailingFallback)
    always_fail = StubAgent("writer", fail_times=99)
    disp = Dispatcher(
        RoutingEngine(registry_with(always_fail)),
        max_retries=1, backoff_base=0, event_bus=bus,
    )
    result = await disp.dispatch(Task(role="writer", prompt="p"))
    assert not result.ok
    assert seen[0] == "agent.assigned"
    assert "agent.retry" in seen
    assert seen[-1] == "agent.failed"


# ─── Tahap 4: Reflection/Consensus modes + Human Approval gate (Bab 25, 26, 61) ─

async def test_orchestrator_reflection_mode_completes_when_confident():
    reg = registry_with(StubAgent("writer", output="jawaban bagus"))
    orch = Orchestrator(agent_registry=reg)
    result = await orch.run("tulis sesuatu", ["writer"], mode="reflection")

    assert not result.escalate
    assert orch.tasks.state_of(result.trace_id) == State.COMPLETED


async def test_orchestrator_voting_mode_wires_through():
    reg = registry_with(
        StubAgent("writer", output="ya"),
        StubAgent("analyst", output="ya"),
        StubAgent("critic", output="ya"),
    )
    orch = Orchestrator(agent_registry=reg)
    result = await orch.run("setuju?", ["writer", "analyst", "critic"], mode="voting")

    assert result.final_output == "ya"
    assert not result.escalate
    assert orch.tasks.state_of(result.trace_id) == State.COMPLETED


async def test_orchestrator_escalates_to_review_and_finalizes_on_approval():
    class UnconfidentAgent(StubAgent):
        async def execute(self, task):
            res = await super().execute(task)
            import dataclasses

            return dataclasses.replace(res, confidence=0.01)

    reg = registry_with(UnconfidentAgent("writer", output="jawaban lemah"))
    orch = Orchestrator(agent_registry=reg)
    result = await orch.run("tulis sesuatu", ["writer"], mode="reflection")

    assert result.escalate
    assert orch.tasks.state_of(result.trace_id) == State.REVIEWING
    assert orch.pending_approvals()[0].trace_id == result.trace_id

    final_state = await orch.finalize_approval(
        result.trace_id, approved=True, decided_by="rudy", reason="acceptable for internal use"
    )
    assert final_state == State.COMPLETED
    assert orch.pending_approvals() == []


async def test_orchestrator_finalize_approval_rejected_cancels_task():
    class UnconfidentAgent(StubAgent):
        async def execute(self, task):
            res = await super().execute(task)
            import dataclasses

            return dataclasses.replace(res, confidence=0.01)

    reg = registry_with(UnconfidentAgent("writer", output="jawaban lemah"))
    orch = Orchestrator(agent_registry=reg)
    result = await orch.run("tulis sesuatu", ["writer"], mode="reflection")

    final_state = await orch.finalize_approval(result.trace_id, approved=False, decided_by="rudy")
    assert final_state == State.CANCELLED


async def test_orchestrator_disabled_human_approval_falls_through(monkeypatch):
    monkeypatch.setattr("api.config.settings.ENABLE_HUMAN_APPROVAL", False)

    class UnconfidentAgent(StubAgent):
        async def execute(self, task):
            res = await super().execute(task)
            import dataclasses

            return dataclasses.replace(res, confidence=0.01)

    reg = registry_with(UnconfidentAgent("writer", output="jawaban lemah"))
    orch = Orchestrator(agent_registry=reg)
    result = await orch.run("tulis sesuatu", ["writer"], mode="reflection")

    assert result.escalate
    # gate disabled: task must still resolve to a terminal state, not hang in REVIEWING.
    assert orch.tasks.state_of(result.trace_id) == State.COMPLETED
    assert orch.pending_approvals() == []


async def test_orchestrator_rejects_disabled_consensus_voting(monkeypatch):
    monkeypatch.setattr("api.config.settings.ENABLE_CONSENSUS_VOTING", False)
    reg = registry_with(StubAgent("writer", output="x"))
    orch = Orchestrator(agent_registry=reg)
    with pytest.raises(ValueError):
        await orch.run("p", ["writer"], mode="voting")


# ─── Tahap 6: Cost budget escalation + telemetry wiring (Bab 27, 34, 61.2) ────

class ExpensiveAgent(StubAgent):
    """Reports real-looking token usage so cost tracking has something to price."""

    async def execute(self, task):
        res = await super().execute(task)
        import dataclasses

        return dataclasses.replace(
            res, provider_used="openai", model_used="gpt-4o", prompt_tokens=1_000_000, completion_tokens=500_000
        )


async def test_orchestrator_tracks_cost_and_escalates_over_budget(monkeypatch):
    monkeypatch.setattr("api.config.settings.COST_BUDGET_PER_TASK", 1.0)
    reg = registry_with(ExpensiveAgent("writer"))
    orch = Orchestrator(agent_registry=reg)

    result = await orch.run("tulis laporan", ["writer"], mode="sequential")

    assert not result.escalate  # confidence itself is fine
    assert orch.tasks.state_of(result.trace_id) == State.REVIEWING
    assert orch.pending_approvals()[0].reason == "cost_budget_exceeded"
    cost = await orch.costs.cost_for_trace(result.trace_id)
    assert cost > 1.0


async def test_orchestrator_under_budget_completes_normally():
    reg = registry_with(StubAgent("writer", output="ok"))
    orch = Orchestrator(agent_registry=reg)

    result = await orch.run("tulis sesuatu", ["writer"], mode="sequential")

    assert orch.tasks.state_of(result.trace_id) == State.COMPLETED
    assert await orch.costs.cost_for_trace(result.trace_id) == 0.0


async def test_orchestrator_metrics_and_tracer_observe_the_run():
    reg = registry_with(StubAgent("writer", output="ok"))
    orch = Orchestrator(agent_registry=reg)

    result = await orch.run("tulis sesuatu", ["writer"], mode="sequential")

    assert orch.metrics.counts["workflow.completed"] == 1
    timeline = await orch.tracer.timeline(result.trace_id)
    assert "workflow.completed" in [s.event_type for s in timeline]
    assert "agent.completed" in [s.event_type for s in timeline]
