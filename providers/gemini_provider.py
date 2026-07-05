"""Google (Gemini) provider — REST adapter via httpx.

Uses the Generative Language API (``:generateContent`` / ``:streamGenerateContent``).
No vendor SDK added (Bab 45.3). Default role: research, vision, documents (Bab 16.3).

Configured but NOT yet exercised against the live API here — activates once
``GOOGLE_API_KEY`` is present.
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


class GeminiProvider(BaseProvider):
    """Provider for Google Gemini generateContent API."""

    name = "gemini"

    def __init__(self, model: str | None = None, api_key: str | None = None, base_url: str | None = None) -> None:
        super().__init__(model or settings.GEMINI_MODEL)
        # `is not None` (not `or`): an explicit api_key="" must mean "no key",
        # not silently fall back to settings — `"" or settings.X` would defeat
        # exactly the override this parameter exists for.
        self._api_key = api_key if api_key is not None else settings.GOOGLE_API_KEY
        self._base_url = (base_url or settings.GEMINI_BASE_URL).rstrip("/")
        self._timeout = settings.PROVIDER_TIMEOUT

    def _require_key(self) -> str:
        if not self._api_key:
            raise ProviderNotConfiguredError("GOOGLE_API_KEY is not set", provider=self.name)
        return self._api_key

    def _payload(self, prompt: str, params: GenerationParams) -> dict[str, Any]:
        gen_config: dict[str, Any] = {
            "temperature": params.temperature,
            "maxOutputTokens": params.max_tokens,
            "topP": params.top_p,
        }
        if params.stop:
            gen_config["stopSequences"] = list(params.stop)
        # Vision (Bab 17.1 role): image parts sit alongside the text part in
        # the same "parts" array — Gemini's multimodal contract, not a
        # separate message.
        parts: list[dict[str, Any]] = [{"text": prompt}]
        for image in params.images:
            parts.append({"inline_data": {"mime_type": image.mime_type, "data": image.data}})
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": gen_config,
        }
        if params.system:
            payload["systemInstruction"] = {"parts": [{"text": params.system}]}
        payload.update(params.extra)
        return payload

    def _url(self, action: str) -> str:
        return f"{self._base_url}/models/{self.model}:{action}?key={self._require_key()}"

    def _extract_text(self, data: dict[str, Any]) -> str:
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(part.get("text", "") for part in parts)

    async def generate(self, prompt: str, params: GenerationParams | None = None) -> ProviderResponse:
        params = params or GenerationParams()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    self._url("generateContent"),
                    headers={"Content-Type": "application/json"},
                    json=self._payload(prompt, params),
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

        usage = data.get("usageMetadata", {})
        candidates = data.get("candidates", [{}])
        return ProviderResponse(
            text=self._extract_text(data),
            provider=self.name,
            model=self.model,
            prompt_tokens=usage.get("promptTokenCount", 0),
            completion_tokens=usage.get("candidatesTokenCount", 0),
            finish_reason=candidates[0].get("finishReason") if candidates else None,
            raw=data,
        )

    async def stream(self, prompt: str, params: GenerationParams | None = None) -> AsyncIterator[Chunk]:
        params = params or GenerationParams()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    self._url("streamGenerateContent") + "&alt=sse",
                    headers={"Content-Type": "application/json"},
                    json=self._payload(prompt, params),
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        try:
                            data = json.loads(line[len("data:"):].strip())
                        except json.JSONDecodeError:
                            continue
                        text = self._extract_text(data)
                        if text:
                            yield Chunk(text=text, done=False)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(str(exc), provider=self.name) from exc
        except httpx.HTTPError as exc:
            raise ProviderResponseError(str(exc), provider=self.name) from exc
        yield Chunk(text="", done=True)

    async def embed(self, text: str) -> list[float]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/models/{settings.GEMINI_EMBED_MODEL}:embedContent?key={self._require_key()}",
                    headers={"Content-Type": "application/json"},
                    json={"content": {"parts": [{"text": text}]}},
                )
                resp.raise_for_status()
                return resp.json()["embedding"]["values"]
        except httpx.HTTPError as exc:
            raise ProviderResponseError(str(exc), provider=self.name) from exc

    async def health_check(self) -> bool:
        if not self._api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}/models?key={self._require_key()}")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
