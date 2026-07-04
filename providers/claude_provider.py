"""Anthropic (Claude) provider — REST adapter via httpx.

Uses the Messages API (``/v1/messages``). No vendor SDK added (Bab 45.3).
Default role: deep analysis, writing, code reasoning, critique (Bab 16.3).

Configured but NOT yet exercised against the live API here — activates once
``ANTHROPIC_API_KEY`` is present.
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from api.config import settings
from core.utils.logger import get_logger

from .base_provider import BaseProvider, Chunk, GenerationParams, ProviderResponse
from .exceptions import (
    ProviderNotConfiguredError,
    ProviderResponseError,
    ProviderTimeoutError,
)

logger = get_logger(__name__)


class ClaudeProvider(BaseProvider):
    """Provider for Anthropic Claude Messages API."""

    name = "claude"

    def __init__(self, model: str | None = None, api_key: str | None = None, base_url: str | None = None) -> None:
        super().__init__(model or settings.CLAUDE_MODEL)
        self._api_key = api_key or settings.ANTHROPIC_API_KEY
        self._base_url = (base_url or settings.ANTHROPIC_BASE_URL).rstrip("/")
        self._timeout = settings.PROVIDER_TIMEOUT

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise ProviderNotConfiguredError("ANTHROPIC_API_KEY is not set", provider=self.name)
        return {
            "x-api-key": self._api_key,
            "anthropic-version": settings.ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

    def _payload(self, prompt: str, params: GenerationParams, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
            "top_p": params.top_p,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
        }
        if params.system:
            payload["system"] = params.system
        if params.stop:
            payload["stop_sequences"] = list(params.stop)
        payload.update(params.extra)
        return payload

    async def generate(self, prompt: str, params: GenerationParams | None = None) -> ProviderResponse:
        params = params or GenerationParams()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/messages",
                    headers=self._headers(),
                    json=self._payload(prompt, params, stream=False),
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(str(exc), provider=self.name) from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderResponseError(
                f"HTTP {exc.response.status_code}: {exc.response.text[:200]}", provider=self.name
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderResponseError(str(exc), provider=self.name) from exc

        try:
            # content is a list of blocks; concatenate text blocks.
            text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
            usage = data.get("usage", {})
        except (KeyError, TypeError) as exc:
            raise ProviderResponseError(f"malformed response: {exc}", provider=self.name) from exc

        return ProviderResponse(
            text=text,
            provider=self.name,
            model=data.get("model", self.model),
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            finish_reason=data.get("stop_reason"),
            raw=data,
        )

    async def stream(self, prompt: str, params: GenerationParams | None = None) -> AsyncIterator[Chunk]:
        params = params or GenerationParams()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/v1/messages",
                    headers=self._headers(),
                    json=self._payload(prompt, params, stream=True),
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        try:
                            event = json.loads(line[len("data:"):].strip())
                        except json.JSONDecodeError:
                            continue
                        if event.get("type") == "content_block_delta":
                            text = event.get("delta", {}).get("text", "")
                            if text:
                                yield Chunk(text=text, done=False)
                        elif event.get("type") == "message_stop":
                            break
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(str(exc), provider=self.name) from exc
        except httpx.HTTPError as exc:
            raise ProviderResponseError(str(exc), provider=self.name) from exc
        yield Chunk(text="", done=True)

    async def health_check(self) -> bool:
        if not self._api_key:
            return False
        try:
            # Minimal 1-token request is the cheapest liveness probe for Messages API.
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/messages",
                    headers=self._headers(),
                    json={"model": self.model, "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]},
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
