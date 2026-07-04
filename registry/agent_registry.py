"""Agent Registry — central catalogue of available agents (MASTER_INSTRUCTION.md Bab 19).

An agent that is not registered cannot be called by the Orchestrator or Routing
Engine. The registry supports lookup by id and by role, and deactivation without
code deletion (feature-flag style rollout, Bab 19).
"""
from __future__ import annotations

from agents.base_agent import BaseAgent
from core.utils.logger import get_logger

from .model_registry import ROLES

logger = get_logger(__name__)


class AgentRegistry:
    """In-memory catalogue of agents keyed by ``agent_id``, indexed by role."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}
        self._by_role: dict[str, list[str]] = {}
        self._inactive: set[str] = set()

    def register(self, agent: BaseAgent) -> None:
        """Register ``agent``. Raises ``ValueError`` on duplicate ``agent_id``."""
        if agent.agent_id in self._agents:
            raise ValueError(f"agent already registered: {agent.agent_id!r}")
        self._agents[agent.agent_id] = agent
        self._by_role.setdefault(agent.role, []).append(agent.agent_id)
        logger.info("agent.register", agent_id=agent.agent_id, role=agent.role)

    def deactivate(self, agent_id: str) -> None:
        """Disable an agent without removing it (Bab 19 feature-flag rollout)."""
        self._inactive.add(agent_id)

    def activate(self, agent_id: str) -> None:
        self._inactive.discard(agent_id)

    def get_by_id(self, agent_id: str) -> BaseAgent:
        if agent_id not in self._agents:
            raise KeyError(f"unknown agent: {agent_id!r}")
        return self._agents[agent_id]

    def get_for_role(self, role: str) -> BaseAgent:
        """Return the first active agent registered for ``role``.

        Raises:
            KeyError: If no active agent is registered for the role.
        """
        for agent_id in self._by_role.get(role, []):
            if agent_id not in self._inactive:
                return self._agents[agent_id]
        raise KeyError(f"no active agent registered for role: {role!r}")

    def has_role(self, role: str) -> bool:
        return any(aid not in self._inactive for aid in self._by_role.get(role, []))

    def list_agents(self) -> list[str]:
        return list(self._agents.keys())

    def list_roles(self) -> list[str]:
        return [role for role in self._by_role if self.has_role(role)]


def build_default_agent_registry(roles: tuple[str, ...] = ROLES) -> AgentRegistry:
    """Build a registry with one :class:`GenericLLMAgent` per role (Bab 17.1).

    Imported lazily to avoid a hard import cycle at module load time.
    """
    from agents.generic_agent import GenericLLMAgent

    registry = AgentRegistry()
    for role in roles:
        registry.register(GenericLLMAgent(role))
    return registry
