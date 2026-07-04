"""Unit tests for the Reflection Engine (Bab 25).

Agents are stubbed — no provider/network calls (Bab 12.3).
"""
import pytest

from agents.base_agent import AgentResult, BaseAgent, Task
from memory.reflection_memory import ReflectionMemory
from memory.stores import InMemoryListStore
from orchestrator.dispatcher import Dispatcher
from orchestrator.reflection import ReflectionEngine
from orchestrator.routing_engine import RoutingEngine
from registry.agent_registry import AgentRegistry


class ScriptedAgent(BaseAgent):
    """Returns confidences from a fixed script, one per call; repeats the last."""

    def __init__(self, role: str, confidences: list[float]) -> None:
        self.role = role
        self.agent_id = f"{role}-scripted"
        self.default_provider = "stub"
        self._confidences = confidences
        self.calls = 0
        self.prompts: list[str] = []

    async def execute(self, task: Task) -> AgentResult:
        self.prompts.append(task.prompt)
        idx = min(self.calls, len(self._confidences) - 1)
        confidence = self._confidences[idx]
        self.calls += 1
        return AgentResult(
            output=f"jawaban-{self.calls}",
            confidence=confidence,
            trace_id=task.trace_id,
            provider_used="stub",
            model_used="stub-m",
            role=self.role,
            agent_id=self.agent_id,
        )

    async def health_check(self) -> bool:
        return True


def _dispatcher_for(agent: BaseAgent) -> Dispatcher:
    registry = AgentRegistry()
    registry.register(agent)
    return Dispatcher(RoutingEngine(registry), max_retries=0)


@pytest.mark.asyncio
async def test_reflection_succeeds_on_first_iteration_when_confident():
    agent = ScriptedAgent("writer", [0.95])
    dispatcher = _dispatcher_for(agent)
    memory = ReflectionMemory(InMemoryListStore())
    engine = ReflectionEngine(dispatcher, memory, max_iterations=3)

    outcome = await engine.run(Task(role="writer", prompt="tulis ringkasan"))

    assert outcome.iterations == 1
    assert not outcome.escalate
    assert outcome.confidence == 0.95
    assert agent.calls == 1


@pytest.mark.asyncio
async def test_reflection_revises_prompt_using_previous_output():
    agent = ScriptedAgent("writer", [0.1, 0.95])
    dispatcher = _dispatcher_for(agent)
    memory = ReflectionMemory(InMemoryListStore())
    engine = ReflectionEngine(dispatcher, memory, max_iterations=3)

    outcome = await engine.run(Task(role="writer", prompt="tulis ringkasan"))

    assert outcome.iterations == 2
    assert not outcome.escalate
    assert agent.calls == 2
    assert "tulis ringkasan" in agent.prompts[1]
    assert "jawaban-1" in agent.prompts[1]  # previous output fed back for revision


@pytest.mark.asyncio
async def test_reflection_escalates_after_exhausting_iterations():
    agent = ScriptedAgent("writer", [0.1, 0.1, 0.1])
    dispatcher = _dispatcher_for(agent)
    memory = ReflectionMemory(InMemoryListStore())
    engine = ReflectionEngine(dispatcher, memory, max_iterations=3)

    outcome = await engine.run(Task(role="writer", prompt="tulis ringkasan"))

    assert outcome.iterations == 3
    assert outcome.escalate
    assert agent.calls == 3


@pytest.mark.asyncio
async def test_reflection_journals_every_iteration_to_memory():
    agent = ScriptedAgent("writer", [0.1, 0.95])
    dispatcher = _dispatcher_for(agent)
    memory = ReflectionMemory(InMemoryListStore())
    engine = ReflectionEngine(dispatcher, memory, max_iterations=3)

    await engine.run(Task(role="writer", prompt="tulis ringkasan", task_id="task-1"))

    entries = await memory.recent("writer")
    assert len(entries) == 2
    assert entries[0]["success"] is False
    assert entries[1]["success"] is True
