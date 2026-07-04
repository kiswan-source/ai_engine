"""Routing Engine — chooses which agent handles a task (MASTER_INSTRUCTION.md Bab 53).

Routing consults the Agent Registry (Bab 19); it never hardcodes a provider in
workflow code (Bab 53.2). A task may name its role directly, or the engine
infers a role from the task type using the Bab 53.1 mapping. Provider selection
per role, and fallback when a provider is down, are handled downstream by the
Model Registry (Bab 20) and Dispatcher/Fallback Strategy (Bab 54).
"""
from __future__ import annotations

from agents.base_agent import BaseAgent, Task
from core.utils.logger import get_logger
from registry.agent_registry import AgentRegistry
from registry.model_registry import ROLES

logger = get_logger(__name__)

# Task type -> agent role (Bab 53.1). Types are advisory hints on Task.metadata.
TASK_TYPE_ROLE: dict[str, str] = {
    "planning": "planner",
    "research": "research",
    "coding": "analyst",
    "code_analysis": "analyst",
    "legal_analysis": "analyst",
    "deep_analysis": "analyst",
    "writing": "writer",
    "review": "reviewer",
    "summary": "memory",
    "guardrail": "guardrail",
    "gis": "tool",
    "document_visual": "vision",
    "pdf": "vision",
    "multimodal": "vision",
}

DEFAULT_ROLE = "writer"


class RoutingError(Exception):
    """Raised when no agent can be routed for a task."""


class RoutingEngine:
    """Resolves a :class:`Task` to a concrete agent."""

    def __init__(self, agent_registry: AgentRegistry) -> None:
        self._registry = agent_registry

    def infer_role(self, task: Task) -> str:
        """Determine the target role for ``task``.

        Priority: an explicit, known ``task.role`` wins; otherwise map
        ``task.metadata['task_type']`` via :data:`TASK_TYPE_ROLE`; else default.
        """
        if task.role and task.role in ROLES:
            return task.role
        task_type = str(task.metadata.get("task_type", "")).lower()
        return TASK_TYPE_ROLE.get(task_type, DEFAULT_ROLE)

    def route(self, task: Task) -> BaseAgent:
        """Return the agent that should execute ``task``.

        Raises:
            RoutingError: If no active agent is registered for the resolved role.
        """
        role = self.infer_role(task)
        try:
            agent = self._registry.get_for_role(role)
        except KeyError as exc:
            raise RoutingError(str(exc)) from exc
        logger.info("routing.route", trace_id=task.trace_id, role=role, agent_id=agent.agent_id)
        return agent
