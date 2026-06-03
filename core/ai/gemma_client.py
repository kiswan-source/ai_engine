"""
Gemma 4:26B client wrapper via Ollama API.
Handles streaming, retries, structured output, and caching.
"""
import asyncio
import hashlib
import json
from typing import AsyncIterator, Optional, Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from api.config import settings
from core.ai.cache import AICache
from core.ai.prompt_templates import PromptTemplate
from core.utils.logger import get_logger

logger = get_logger(__name__)


class GemmaClient:
    """Async Gemma 4:26B client with streaming, retry, and caching."""

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.GEMMA_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT
        self.cache = AICache()
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    def _get_client(self) -> httpx.AsyncClient:
        if not self._client:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(600.0, connect=10.0),
            )
        return self._client

    def _cache_key(self, prompt: str, system: str = "", **kwargs) -> str:
        raw = f"{self.model}:{system}:{prompt}:{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @retry(
        stop=stop_after_attempt(settings.OLLAMA_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        use_cache: bool = True,
    ) -> str:
        """Single-shot generation with optional cache."""
        cache_key = self._cache_key(prompt, system, temperature=temperature)

        if use_cache:
            cached = await self.cache.get(cache_key)
            if cached:
                logger.debug("Cache hit", key=cache_key[:16])
                return cached

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        client = self._get_client()
        response = await client.post("/api/generate", json=payload)
        response.raise_for_status()

        result = response.json()["response"]

        if use_cache:
            await self.cache.set(cache_key, result, ttl=settings.AI_CACHE_TTL)

        logger.info(
            "Gemma generation complete",
            model=self.model,
            prompt_len=len(prompt),
            response_len=len(result),
        )
        return result

    async def stream(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """Streaming generation — yields tokens as they arrive."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": True,
            "options": {"temperature": temperature},
        }

        client = self._get_client()
        async with client.stream("POST", "/api/generate", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line:
                    chunk = json.loads(line)
                    yield chunk.get("response", "")
                    if chunk.get("done"):
                        break

    async def generate_json(
        self,
        prompt: str,
        schema_hint: str = "",
        system: str = "",
        temperature: float = 0.3,
    ) -> dict:
        """
        Force structured JSON output.
        Adds system instruction + parses response safely.
        """
        json_system = (
            f"{system}\n\n"
            "IMPORTANT: Respond ONLY with valid JSON. No markdown, no explanation. "
            f"Schema hint: {schema_hint}"
        ).strip()

        raw = await self.generate(
            prompt=prompt,
            system=json_system,
            temperature=temperature,
            use_cache=False,
        )

        # Strip markdown fences if model wraps output
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        clean = clean.strip().rstrip("```").strip()

        try:
            return json.loads(clean)
        except json.JSONDecodeError as e:
            logger.warning("JSON parse failed, returning raw text", error=str(e))
            return {"raw": raw, "parse_error": str(e)}

    async def embed(self, text: str) -> list[float]:
        """Generate embeddings via Ollama embed endpoint."""
        client = self._get_client()
        response = await client.post(
            "/api/embed",
            json={"model": self.model, "input": text},
        )
        response.raise_for_status()
        return response.json()["embeddings"][0]

    async def health_check(self) -> dict:
        """Check if Ollama + model are available."""
        try:
            client = self._get_client()
            resp = await client.get("/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            gemma_ready = any(self.model.split(":")[0] in m for m in models)
            return {
                "ollama": "ok",
                "model": self.model,
                "model_loaded": gemma_ready,
                "available_models": models,
            }
        except Exception as e:
            return {"ollama": "error", "detail": str(e)}


# Singleton instance
gemma = GemmaClient()
