"""GenericLLMAgent — a provider-agnostic, role-driven agent.

One concrete agent that fulfils any role by resolving its provider from the
Model Registry (Bab 20) via the provider factory (Bab 16.2). It is deliberately
provider-agnostic (Bab 17): the folder/role assignment is a default, not a
hard binding. Specialised agents (Planner, Vision, …) will subclass/replace this
in later phases; for Tahap 2 it makes the orchestrator runnable end-to-end.

Confidence here is a lightweight heuristic placeholder — real Confidence Scoring
(Bab 28) arrives in Tahap 4. Cost is 0.0 until the Cost Tracker (Bab 27, Tahap 6).
"""
from __future__ import annotations

from core.utils.logger import get_logger
from providers import GenerationParams, create_for_role
from providers.base_provider import BaseProvider

from .base_agent import AgentResult, BaseAgent, Task

logger = get_logger(__name__)


def _estimate_confidence(text: str, finish_reason: str | None) -> float:
    """Heuristic placeholder confidence in [0.0, 1.0] (Bab 28 supersedes this)."""
    if not text.strip():
        return 0.0
    if finish_reason in ("length", "MAX_TOKENS"):
        return 0.5  # truncated output — less trustworthy
    return 0.8


class GenericLLMAgent(BaseAgent):
    """LLM agent that executes a prompt for a given role."""

    def __init__(self, role: str, provider: BaseProvider | None = None, prefer_fallback: bool = False) -> None:
        self.role = role
        self.agent_id = f"{role}-agent" + ("-fallback" if prefer_fallback else "")
        self._prefer_fallback = prefer_fallback
        self._provider = provider or create_for_role(role, prefer_fallback=prefer_fallback)
        self.default_provider = self._provider.name

    @property
    def provider(self) -> BaseProvider:
        return self._provider

    async def execute(self, task: Task) -> AgentResult:
        """Run the task against the resolved provider.

        Raises:
            ProviderError: Propagated on provider failure so the Dispatcher can
                apply the Fallback Strategy (Bab 54); the agent does not swallow it.
        """
        params = GenerationParams(
            system=task.system,
            temperature=task.temperature,
            max_tokens=task.max_tokens,
        )
        resp = await self._provider.generate(task.prompt, params)
        confidence = _estimate_confidence(resp.text, resp.finish_reason)
        logger.info(
            "agent.execute",
            agent_id=self.agent_id,
            role=self.role,
            provider=resp.provider,
            trace_id=task.trace_id,
            confidence=confidence,
        )
        return AgentResult(
            output=resp.text,
            confidence=confidence,
            trace_id=task.trace_id,
            provider_used=resp.provider,
            model_used=resp.model,
            cost=0.0,
            agent_id=self.agent_id,
            role=self.role,
            degraded=self._prefer_fallback,
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
        )

    async def health_check(self) -> bool:
        return await self._provider.health_check()
