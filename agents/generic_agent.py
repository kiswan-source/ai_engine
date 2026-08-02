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
provider's ACTUAL configured endpoint is external.

Fase 1 (SEC-4, DCF_SECURITY_AUDIT_2026-07-11.md temuan #4): the check above
used to be ``provider.name != "ollama"`` — wrong on two live deployment
modes at once, since "ollama" the name says nothing about where
``OLLAMA_BASE_URL`` actually points (Docker Compose's is the WSL host's
virtual-network IP, not loopback; the Kubernetes manifest set lets it be
any host). Replaced with ``security.endpoint_policy.is_internal_endpoint``,
which classifies the provider's real ``base_url`` (loopback/private-range/
well-known-internal-suffix vs. everything else) — see that module's
docstring for the full rationale. Same fix applied to ``core/chat/engine.py``
and ``agent/core.py``, the two HTTP-facing agent paths, which call Ollama
directly and never had any PII-redaction check at all until now.

Tahap 34 (Bab 68 Prioritas 13, Security Dashboard): PII redaction now also
calls ``security.audit_log.record("pii.redacted", ...)`` when
``detect_pii()`` actually finds something — previously the only guardrail
action here that never reached the audit trail at all, which would have
left a Security Dashboard permanently blank for this category. Only
logged when matches exist, so the trail doesn't fill with "redacted
nothing" noise on every external-provider call.

Fase 14 (DCF v5 mandate — orchestrator agent tool access, Gate 1 Owner
decision 2026-08-02): EXECUTOR-capability roles ("writer", "tool" — see
``agents/capabilities.py``) now get real ``ToolRegistry`` access during
``execute()``, so an orchestrator workflow can actually read a document
(read_pdf/read_docx/workspace reads) and produce a real file artifact
(write_docx/write_pdf/etc.), not just text — closing the gap CLAUDE.md §2/§9
used to only partially disclose. VALIDATOR-capability roles (reviewer/critic/
consensus/guardrail/reflection/confidence) are structurally excluded by the
same capability check, so builder/validator independence (Fase 2, R-08) holds
for free. Mechanically: build a fresh ``ToolRegistry`` (same pattern
``agent/tools/registry.py::build_registry`` already documents — "a FRESH
registry per call", not a shared mutable singleton), pass the curated
``agent/tools/tool_schemas.py::TOOL_SCHEMAS`` (minus ``run_orchestrated_
workflow`` itself — a deliberate recursion guard, not part of the Gate 1
tool-scope decision, added to prevent an EXECUTOR step from spawning
unbounded nested orchestrator runs) as ``GenerationParams.tools``, and let
the resolved provider's own tool-calling loop (today: only
``OllamaProvider._generate_with_tools``; other providers silently ignore
``tools`` and generate plain text — the Gate 1-approved graceful degrade)
execute calls via ``ToolRegistry.execute(name, args, role=caller_role)`` —
the SAME RBAC chokepoint ``agent/core.py`` and ``core/chat/engine.py``
already gate through. ``caller_role`` is threaded from whoever calls
``Orchestrator.run(..., caller_role=...)`` down through ``Task.metadata`` —
never invented here, never trusted from the model. Gated behind
``settings.ENABLE_ORCHESTRATOR_AGENT_TOOLS`` (default ``True``). Owner
explicitly chose the full ``ToolRegistry`` (not a curated document-only
subset) and chose to allow this in every workflow mode including
voting/consensus/reflection (accepting the documented race/duplicate-write
risk from those modes' concurrent/repeated same-role dispatch, rather than
restricting to sequential/parallel only) — see the Fase 14 Gate 1 record for
the full option set presented and the rationale for each recommendation.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from core.utils.logger import get_logger
from providers import GenerationParams, ImageInput, create_for_role
from providers.base_provider import BaseProvider
from security.endpoint_policy import is_internal_endpoint

from .base_agent import AgentResult, BaseAgent, Task
from .capabilities import AgentCapability, capability_for

logger = get_logger(__name__)

# Fase 14 Gate 2 finding: tools an EXECUTOR-capability step must never be
# able to invoke even if a model hallucinates a call to a name it wasn't
# offered — enforced in the executor itself, not just by omission from the
# advertised schema list (see _build_tool_access).
_RECURSION_GUARDED_TOOLS = frozenset({"run_orchestrated_workflow"})


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
        from security import audit_log, check_prompt, detect_pii, redact_pii, validate

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

        if settings.ENABLE_PII_REDACTION and not is_internal_endpoint(self._provider.base_url):
            pii_matches = detect_pii(prompt)
            if pii_matches:
                prompt = redact_pii(prompt)
                await audit_log.record(
                    "pii.redacted",
                    actor=self.agent_id,
                    detail={"categories": sorted({m.category for m in pii_matches}), "count": len(pii_matches), "role": self.role},
                    trace_id=task.trace_id,
                )

        # Vision (Bab 17.1 role): images travel via Task.payload rather than a
        # named Task field — it's already documented as the "arbitrary
        # structured input" extension point (base_agent.py), so this role
        # stays as provider-agnostic as every other one.
        images = tuple(ImageInput(**img) for img in task.payload.get("images", ()))

        tools: tuple[dict, ...] = ()
        tool_executor = None
        if settings.ENABLE_ORCHESTRATOR_AGENT_TOOLS and capability_for(self.role) == AgentCapability.EXECUTOR:
            tools, tool_executor = self._build_tool_access(task)

        params = GenerationParams(
            system=task.system,
            temperature=task.temperature,
            max_tokens=task.max_tokens,
            images=images,
            tools=tools,
            tool_executor=tool_executor,
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
            tool_calls=resp.tool_calls_made,
        )

    async def health_check(self) -> bool:
        return await self._provider.health_check()

    def _build_tool_access(
        self, task: Task
    ) -> tuple[tuple[dict, ...], Callable[[str, dict], Awaitable[object]]]:
        """Tool schemas + executor for an EXECUTOR-capability step (Fase 14).

        ``caller_role`` comes only from ``task.metadata`` — set by
        ``orchestrator/planner.py`` from whatever ``Orchestrator.run(...,
        caller_role=...)`` was given by its caller (``api/routes/
        orchestrator.py``'s authenticated principal, or the chat session's
        RBAC role via ``agent/tools/orchestrator_tools.py``). Never taken
        from the task prompt/payload — same never-trust-the-model rule
        ``core/chat/engine.py`` already applies to ``workspace_id``/``owner``.
        """
        from agent.tools.registry import build_registry
        from agent.tools.tool_schemas import TOOL_SCHEMAS
        from api.config import settings

        caller_role = task.metadata.get("caller_role")
        registry = build_registry(settings.OLLAMA_BASE_URL, settings.GEMMA_MODEL)
        # Recursion guard (Gate 1 finding, applied within the Owner-approved
        # "full ToolRegistry" scope, not a narrowing of it): an EXECUTOR step
        # must never be able to spawn a brand new, unbounded
        # Orchestrator.run() from inside itself. Filtering the SCHEMA list
        # below only stops a well-behaved model from being offered the
        # choice — it does NOT stop a hallucinated tool_call naming a tool
        # that was never advertised (Ollama's native tool-calling does not
        # guarantee the model only ever calls something it was shown; this
        # was a real Gate 2 finding, not a hypothetical). The actual
        # enforcement has to be in the executor itself.
        schemas = tuple(s for s in TOOL_SCHEMAS if s["function"]["name"] not in _RECURSION_GUARDED_TOOLS)

        async def _tool_executor(name: str, args: dict):
            if name in _RECURSION_GUARDED_TOOLS:
                return {
                    "success": False,
                    "error": f"Tool '{name}' tidak tersedia di dalam langkah orchestrator "
                             "(mencegah rekursi tak terbatas).",
                }
            return await asyncio.to_thread(registry.execute, name, args, caller_role)

        return schemas, _tool_executor
