"""OpenAI (ChatGPT) provider — REST adapter via httpx.

No vendor SDK is added (Bab 45.3 — avoid new third-party deps); the Chat
Completions REST contract is stable and httpx is already a dependency. Default
role: orchestration, planning, review, QA (Bab 16.3).

Configured but NOT yet exercised against the live API in this environment — it
activates automatically once ``OPENAI_API_KEY`` is present in the environment.
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


class OpenAIProvider(BaseProvider):
    """Provider for OpenAI Chat Completions API."""

    name = "openai"

    def __init__(self, model: str | None = None, api_key: str | None = None, base_url: str | None = None) -> None:
        super().__init__(model or settings.OPENAI_MODEL)
        # `is not None` (not `or`): an explicit api_key="" must mean "no key",
        # not silently fall back to settings — `"" or settings.X` would defeat
        # exactly the override this parameter exists for.
        self._api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self._base_url = (base_url or settings.OPENAI_BASE_URL).rstrip("/")
        self._timeout = settings.PROVIDER_TIMEOUT

    def _require_key(self) -> str:
        if not self._api_key:
            raise ProviderNotConfiguredError("OPENAI_API_KEY is not set", provider=self.name)
        return self._api_key

    def _messages(self, prompt: str, params: GenerationParams) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if params.system:
            messages.append({"role": "system", "content": params.system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _payload(self, prompt: str, params: GenerationParams, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._messages(prompt, params),
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
            "top_p": params.top_p,
            "stream": stream,
        }
        if params.stop:
            payload["stop"] = list(params.stop)
        payload.update(params.extra)
        return payload

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._require_key()}", "Content-Type": "application/json"}

    async def generate(self, prompt: str, params: GenerationParams | None = None) -> ProviderResponse:
        params = params or GenerationParams()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
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
            choice = data["choices"][0]
            text = choice["message"]["content"]
            usage = data.get("usage", {})
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError(f"malformed response: {exc}", provider=self.name) from exc

        return ProviderResponse(
            text=text,
            provider=self.name,
            model=data.get("model", self.model),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            finish_reason=choice.get("finish_reason"),
            raw=data,
        )

    async def stream(self, prompt: str, params: GenerationParams | None = None) -> AsyncIterator[Chunk]:
        params = params or GenerationParams()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=self._payload(prompt, params, stream=True),
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            break
                        try:
                            delta = json.loads(data)["choices"][0]["delta"].get("content", "")
                        except (KeyError, IndexError, json.JSONDecodeError):
                            continue
                        if delta:
                            yield Chunk(text=delta, done=False)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(str(exc), provider=self.name) from exc
        except httpx.HTTPError as exc:
            raise ProviderResponseError(str(exc), provider=self.name) from exc
        yield Chunk(text="", done=True)

    async def embed(self, text: str) -> list[float]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/embeddings",
                    headers=self._headers(),
                    json={"model": settings.OPENAI_EMBED_MODEL, "input": text},
                )
                resp.raise_for_status()
                return resp.json()["data"][0]["embedding"]
        except httpx.HTTPError as exc:
            raise ProviderResponseError(str(exc), provider=self.name) from exc

    async def health_check(self) -> bool:
        if not self._api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}/models", headers=self._headers())
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
