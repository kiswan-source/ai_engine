"""Agent domain model + base interface (MASTER_INSTRUCTION.md Bab 17, 48, AGENT_SPECIFICATION.md).

``Task`` and ``AgentResult`` are the shared domain objects (DDD, Bab 4.4) that
flow between the Orchestrator (Bab 18) and agents. They live here — the agents
tier — so both the orchestrator (which depends on agents) and the agents
themselves can use them without reversing the dependency direction
(``orchestrator → agents → providers/registry → core``, Bab 4.1).
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


def new_id() -> str:
    """Generate a short unique id (task/trace)."""
    return uuid.uuid4().hex


@dataclass
class Task:
    """A single unit of work dispatched to one agent.

    Attributes:
        role: Target agent role (see ``registry.model_registry.ROLES``).
        prompt: The instruction/content for the agent.
        task_id: Unique task identifier.
        trace_id: Correlates all work belonging to one user request (Bab 11).
        system: Optional system prompt override.
        temperature / max_tokens: Generation knobs.
        payload: Arbitrary structured input (e.g. file refs, prior outputs).
        metadata: Free-form routing/telemetry hints.
    """

    role: str
    prompt: str
    task_id: str = field(default_factory=new_id)
    trace_id: str = field(default_factory=new_id)
    system: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentResult:
    """Structured result of an agent execution.

    Per AGENT_SPECIFICATION §5 every result carries ``output``, ``confidence``,
    ``trace_id``, ``provider_used`` and ``cost`` so it can be consumed uniformly
    by the Consensus Engine (Bab 26) and Observability (Bab 34).
    """

    output: str
    confidence: float
    trace_id: str
    provider_used: str
    model_used: str
    cost: float = 0.0
    agent_id: str = ""
    role: str = ""
    degraded: bool = False
    error: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def ok(self) -> bool:
        return self.error is None


class BaseAgent(ABC):
    """Interface every AI_ENGINE agent implements (AGENT_SPECIFICATION §5).

    Attributes:
        agent_id: Unique, stable agent identifier used by the Agent Registry (Bab 19).
        role: The role this agent fulfils (Bab 17).
        default_provider: Provider name this agent defaults to (from Model Registry, Bab 20).
    """

    agent_id: str
    role: str
    default_provider: str

    @abstractmethod
    async def execute(self, task: Task) -> AgentResult:
        """Execute ``task`` and return a structured :class:`AgentResult`."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Report whether the agent is ready to accept new tasks."""
        raise NotImplementedError
