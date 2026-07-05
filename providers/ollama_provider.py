"""Ollama (Gemma Local) provider — the real, production-wired integration.

Reuses the existing, battle-tested ``core.ai.gemma_client.GemmaClient`` rather
than re-implementing HTTP calls (Bab 3 — Reuse Existing Module). Default role:
memory, summarisation, guardrail, and low-cost/on-prem tasks (Bab 16.3).
"""
from __future__ import annotations

from typing import AsyncIterator

import httpx

from api.config import settings
from core.ai.gemma_client import GemmaClient
from core.utils.logger import get_logger

from .base_provider import BaseProvider, Chunk, GenerationParams, ProviderResponse
from .exceptions import ProviderResponseError, ProviderTimeoutError

logger = get_logger(__name__)


class OllamaProvider(BaseProvider):
    """Local LLM provider backed by Ollama (default: Gemma)."""

    name = "ollama"

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        super().__init__(model or settings.GEMMA_MODEL)
        self._client = GemmaClient()
        # GemmaClient reads model/base_url from settings; override so the model
        # registry (Bab 20) can pick a specific local model per role.
        self._client.model = self.model
        if base_url:
            self._client.base_url = base_url

    async def generate(self, prompt: str, params: GenerationParams | None = None) -> ProviderResponse:
        params = params or GenerationParams()
        try:
            text = await self._client.generate(
                prompt=prompt,
                system=params.system,
                temperature=params.temperature,
                max_tokens=params.max_tokens,
                use_cache=params.use_cache,
                images=[image.data for image in params.images] or None,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(str(exc), provider=self.name) from exc
        except httpx.HTTPError as exc:
            raise ProviderResponseError(str(exc), provider=self.name) from exc

        return ProviderResponse(
            text=text,
            provider=self.name,
            model=self.model,
            prompt_tokens=self.count_tokens(params.system + prompt),
            completion_tokens=self.count_tokens(text),
            finish_reason="stop",
        )

    async def stream(self, prompt: str, params: GenerationParams | None = None) -> AsyncIterator[Chunk]:
        params = params or GenerationParams()
        try:
            async for token in self._client.stream(
                prompt=prompt,
                system=params.system,
                temperature=params.temperature,
            ):
                yield Chunk(text=token, done=False)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(str(exc), provider=self.name) from exc
        except httpx.HTTPError as exc:
            raise ProviderResponseError(str(exc), provider=self.name) from exc
        yield Chunk(text="", done=True)

    async def embed(self, text: str) -> list[float]:
        try:
            return await self._client.embed(text)
        except httpx.HTTPError as exc:
            raise ProviderResponseError(str(exc), provider=self.name) from exc

    async def health_check(self) -> bool:
        result = await self._client.health_check()
        return result.get("ollama") == "ok"
