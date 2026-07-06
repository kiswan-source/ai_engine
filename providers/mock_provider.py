"""Mock Provider (Bab 68 Backlog Prioritas 16, Tahap 36) — the real, reusable
mock the Simulation Mode roadmap item calls for, as opposed to the ad-hoc
``StubProvider``/fake classes each test file previously had to define for
itself. Returns a deterministic, instant, zero-cost response with no network
call at all — used by ``registry/agent_registry.py::build_simulation_agent_registry``
to back every role for a dry-run ``Orchestrator.run(..., simulate=True)``.

Note on Bab 16.2/45.5 ("never instantiate a concrete provider directly in
business logic, always go through the factory"): that rule protects against
scattering real-vendor config resolution outside ``provider_factory.py``.
This class deliberately has no vendor config to resolve — it's constructed
directly via ``GenericLLMAgent``'s existing ``provider=`` override parameter
(the same extension point every test's fake provider already uses), not
smuggled in as a real provider choice anywhere the factory would normally
be consulted.
"""
from __future__ import annotations

from typing import AsyncIterator

from .base_provider import BaseProvider, Chunk, GenerationParams, ProviderResponse


class MockProvider(BaseProvider):
    """Deterministic, zero-cost, zero-network stand-in for any real provider."""

    name = "mock"

    def __init__(self, model: str = "mock-model") -> None:
        super().__init__(model)

    def _simulated_text(self, prompt: str) -> str:
        preview = prompt.strip().replace("\n", " ")[:80]
        return f"[SIMULASI] Respons tiruan untuk prompt ({len(prompt)} karakter): {preview}"

    async def generate(self, prompt: str, params: GenerationParams | None = None) -> ProviderResponse:
        params = params or GenerationParams()
        text = self._simulated_text(prompt)
        return ProviderResponse(
            text=text,
            provider=self.name,
            model=self.model,
            prompt_tokens=self.count_tokens(params.system + prompt),
            completion_tokens=self.count_tokens(text),
            # "stop", not "length"/None — agents/generic_agent.py's
            # _estimate_confidence treats a truncated finish_reason as lower
            # confidence; a simulated run should read as a normal success.
            finish_reason="stop",
        )

    async def stream(self, prompt: str, params: GenerationParams | None = None) -> AsyncIterator[Chunk]:
        yield Chunk(text=self._simulated_text(prompt), done=False)
        yield Chunk(text="", done=True)

    async def health_check(self) -> bool:
        return True
