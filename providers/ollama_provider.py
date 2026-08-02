"""Ollama (Gemma Local) provider — the real, production-wired integration.

Reuses the existing, battle-tested ``core.ai.gemma_client.GemmaClient`` rather
than re-implementing HTTP calls (Bab 3 — Reuse Existing Module). Default role:
memory, summarisation, guardrail, and low-cost/on-prem tasks (Bab 16.3).
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from api.config import settings
from core.ai.gemma_client import GemmaClient
from core.utils.logger import get_logger

from .base_provider import BaseProvider, Chunk, GenerationParams, ProviderResponse
from .exceptions import ProviderResponseError, ProviderTimeoutError

logger = get_logger(__name__)

# Fase 14 (DCF v5 mandate — orchestrator agent tool access): bounds on the
# native tool-calling round-loop, same values/rationale as
# ``core/chat/engine.py``'s ``MAX_TOOL_ROUNDS``/``TOOL_RESULT_MAX_CHARS`` —
# kept as separate constants (not imported from ``core/chat/``) because
# ``providers/`` sits below ``core/chat/`` in the dependency direction and
# must not import from it (see ``agent/tools/tool_schemas.py`` for the same
# rule applied to the schema list itself).
_MAX_TOOL_ROUNDS = 5
_TOOL_RESULT_MAX_CHARS = 12000


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

    @property
    def base_url(self) -> str:
        return self._client.base_url

    async def generate(self, prompt: str, params: GenerationParams | None = None) -> ProviderResponse:
        params = params or GenerationParams()
        if params.tools and params.tool_executor:
            # Native tool-calling needs Ollama's chat-style `/api/chat`
            # endpoint (message history + tools), unlike the single-prompt
            # `/api/generate` GemmaClient wraps below — see this module's
            # class docstring context / Fase 14 Gate 1 finding #1 for why
            # this can't reuse GemmaClient as-is.
            return await self._generate_with_tools(prompt, params)
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

    async def _generate_with_tools(self, prompt: str, params: GenerationParams) -> ProviderResponse:
        """Self-contained native tool-calling loop against Ollama's `/api/chat`.

        Executes every tool call via ``params.tool_executor`` and feeds the
        result back as a ``role: tool`` message, up to ``_MAX_TOOL_ROUNDS``
        rounds, returning only once the model stops requesting tools (or the
        round budget is exhausted). Callers (``agents/generic_agent.py``) see
        one ``generate()`` call in, one final answer out — the round-trip
        mechanics stay entirely inside this provider, same shape as every
        other ``generate()`` call.
        """
        messages: list[dict[str, Any]] = []
        if params.system:
            messages.append({"role": "system", "content": params.system})
        messages.append({"role": "user", "content": prompt})

        tool_calls_made: list[dict[str, Any]] = []
        last_content = ""
        timeout = httpx.Timeout(settings.OLLAMA_TIMEOUT, connect=10.0)
        try:
            async with httpx.AsyncClient(base_url=self._client.base_url, timeout=timeout) as client:
                for _round in range(_MAX_TOOL_ROUNDS):
                    resp = await client.post(
                        "/api/chat",
                        json={
                            "model": self.model,
                            "messages": messages,
                            "tools": list(params.tools),
                            "stream": False,
                            "options": {
                                "temperature": params.temperature,
                                "num_predict": params.max_tokens,
                                # Fase 15 fix: this call was missing num_ctx entirely,
                                # silently falling back to Ollama's 4096-token default
                                # instead of the value core/chat/engine.py already
                                # standardizes on (see settings.OLLAMA_NUM_CTX's own
                                # docstring for why 4096 is too small in practice).
                                "num_ctx": settings.OLLAMA_NUM_CTX,
                            },
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    msg = data.get("message", {}) or {}
                    last_content = msg.get("content", "") or ""
                    tcs = msg.get("tool_calls") or []

                    assistant_msg: dict[str, Any] = {"role": "assistant", "content": last_content}
                    if tcs:
                        assistant_msg["tool_calls"] = tcs
                    messages.append(assistant_msg)

                    if not tcs:
                        break

                    for tc in tcs:
                        fn = tc.get("function", {}) or {}
                        tool_name = fn.get("name", "")
                        tool_args = fn.get("arguments", {}) or {}
                        try:
                            result = await params.tool_executor(tool_name, tool_args)
                        except Exception as exc:  # noqa: BLE001 — a failing tool must not kill the round-loop
                            result = {"success": False, "error": str(exc)}
                        ok = not (isinstance(result, dict) and (result.get("success") is False or "error" in result))
                        file_path = result.get("file") if isinstance(result, dict) else None
                        tool_calls_made.append(
                            {"name": tool_name, "args": tool_args, "success": ok, "file": file_path}
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "content": json.dumps(result, ensure_ascii=False, default=str)[:_TOOL_RESULT_MAX_CHARS],
                            }
                        )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(str(exc), provider=self.name) from exc
        except httpx.HTTPError as exc:
            raise ProviderResponseError(str(exc), provider=self.name) from exc

        return ProviderResponse(
            text=last_content,
            provider=self.name,
            model=self.model,
            prompt_tokens=self.count_tokens(params.system + prompt),
            completion_tokens=self.count_tokens(last_content),
            finish_reason="stop",
            tool_calls_made=tuple(tool_calls_made),
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
