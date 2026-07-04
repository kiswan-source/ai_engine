"""GenericLLMAgent — a provider-agnostic, role-driven agent.

One concrete agent that fulfils any role by resolving its provider from the
Model Registry (Bab 20) via the provider factory (Bab 16.2). It is deliberately
provider-agnostic (Bab 17): the folder/role assignment is a default, not a
hard binding. Specialised agents (Planner, Vision, …) will subclass/replace this
in later phases; for Tahap 2 it makes the orchestrator runnable end-to-end.

Confidence here is a lightweight heuristic placeholder — real Confidence Scoring
(Bab 28) arrives in Tahap 4. Cost is 0.0 until the Cost Tracker (Bab 27, Tahap 6).

Tahap 7: every dispatch passes through ``security.prompt_guard`` (Bab 30 rule
1) before generation and ``security.output_validator`` after — this is the
one choke point every role shares, so it's the one place these guardrails
need wiring rather than duplicating checks per provider. PII redaction (Bab
30 — "sebelum dikirim ke provider eksternal") only applies when the resolved
provider isn't Ollama (local, never leaves the system).
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
        """Run the task against the resolved provider, guarded on both sides (Bab 30).

        Raises:
            ProviderError: Propagated on provider failure so the Dispatcher can
                apply the Fallback Strategy (Bab 54); the agent does not swallow it.
        """
        from api.config import settings
        from security import audit_log, check_prompt, redact_pii, validate

        prompt = task.prompt

        if settings.ENABLE_PROMPT_GUARD:
            guard = check_prompt(prompt)
            if guard.blocked:
                await audit_log.record(
                    "prompt_guard.blocked",
                    actor=self.agent_id,
                    detail={"matches": guard.matches, "score": guard.score, "role": self.role},
                    trace_id=task.trace_id,
                )
                logger.warning(
                    "agent.prompt_blocked", agent_id=self.agent_id, trace_id=task.trace_id, matches=guard.matches
                )
                return AgentResult(
                    output="",
                    confidence=0.0,
                    trace_id=task.trace_id,
                    provider_used=self._provider.name,
                    model_used=self._provider.model,
                    agent_id=self.agent_id,
                    role=self.role,
                    degraded=True,
                    guardrail_blocked=True,
                    error=f"blocked by prompt_guard: {', '.join(guard.matches)}",
                )
            if guard.suspicious:
                await audit_log.record(
                    "prompt_guard.neutralized",
                    actor=self.agent_id,
                    detail={"matches": guard.matches, "score": guard.score, "role": self.role},
                    trace_id=task.trace_id,
                )
                prompt = guard.sanitized_text

        if settings.ENABLE_PII_REDACTION and self._provider.name != "ollama":
            prompt = redact_pii(prompt)

        params = GenerationParams(
            system=task.system,
            temperature=task.temperature,
            max_tokens=task.max_tokens,
        )
        resp = await self._provider.generate(prompt, params)
        confidence = _estimate_confidence(resp.text, resp.finish_reason)

        guardrail_score: float | None = None
        if settings.ENABLE_OUTPUT_VALIDATION:
            validation = validate(resp.text, resp.finish_reason)
            guardrail_score = validation.score
            if not validation.ok:
                await audit_log.record(
                    "output_validator.violation",
                    actor=self.agent_id,
                    detail={"violations": validation.violations, "role": self.role},
                    trace_id=task.trace_id,
                )

        logger.info(
            "agent.execute",
            agent_id=self.agent_id,
            role=self.role,
            provider=resp.provider,
            trace_id=task.trace_id,
            confidence=confidence,
            guardrail_score=guardrail_score,
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
            guardrail_score=guardrail_score,
        )

    async def health_check(self) -> bool:
        return await self._provider.health_check()
