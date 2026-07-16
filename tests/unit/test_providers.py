"""Unit tests for the provider layer (MASTER_INSTRUCTION.md Bab 16).

All external LLM calls are mocked — no live network access (Bab 12.3).
"""
import httpx
import pytest

from providers import (
    ClaudeProvider,
    GeminiProvider,
    GenerationParams,
    ImageInput,
    OllamaProvider,
    OpenAIProvider,
    ProviderNotConfiguredError,
    ProviderResponse,
    UnknownProviderError,
    create_provider,
)
from providers.base_provider import BaseProvider, Chunk
from providers.exceptions import AIEngineError, ProviderError


# ─── Value objects ────────────────────────────────────────────────────────────

def test_generation_params_defaults():
    p = GenerationParams()
    assert p.temperature == 0.7
    assert p.max_tokens == 2048
    assert p.system == ""
    assert p.use_cache is True
    assert p.images == ()


def test_provider_response_total_tokens():
    r = ProviderResponse(text="hi", provider="ollama", model="m", prompt_tokens=3, completion_tokens=5)
    assert r.total_tokens == 8


def test_count_tokens_heuristic():
    prov = OllamaProvider(model="test")
    assert prov.count_tokens("") == 0
    assert prov.count_tokens("abcd") == 1
    assert prov.count_tokens("a" * 40) == 10


# ─── base_url (Fase 1, SEC-4 — security.endpoint_policy reads this) ───────────

def test_ollama_base_url_reflects_configured_endpoint():
    prov = OllamaProvider(model="test", base_url="http://172.29.239.93:11434")
    assert prov.base_url == "http://172.29.239.93:11434"


def test_openai_base_url_defaults_to_settings():
    prov = OpenAIProvider(model="gpt-4o", api_key="")
    assert prov.base_url.startswith("https://api.openai.com")


def test_claude_base_url_defaults_to_settings():
    prov = ClaudeProvider(model="claude-sonnet-5", api_key="")
    assert prov.base_url.startswith("https://api.anthropic.com")


def test_gemini_base_url_defaults_to_settings():
    prov = GeminiProvider(model="gemini-1.5-pro", api_key="")
    assert prov.base_url.startswith("https://generativelanguage.googleapis.com")


def test_openai_base_url_honors_explicit_override():
    prov = OpenAIProvider(model="gpt-4o", api_key="", base_url="https://internal-proxy.local/v1")
    assert prov.base_url == "https://internal-proxy.local/v1"


def test_base_provider_default_base_url_is_empty():
    """A provider that never sets ``_base_url`` (e.g. a bare BaseProvider
    subclass) must not crash — empty string, fail-closed via
    endpoint_policy.is_internal_endpoint (treated as external)."""

    class _Bare(BaseProvider):
        name = "bare"

        async def generate(self, prompt, params=None):
            raise NotImplementedError

        async def stream(self, prompt, params=None):
            raise NotImplementedError
            yield  # pragma: no cover

        async def health_check(self):
            return True

    assert _Bare(model="x").base_url == ""


def test_exception_hierarchy():
    assert issubclass(ProviderError, AIEngineError)
    err = ProviderError("boom", provider="openai")
    assert "openai" in str(err)


# ─── Ollama provider (real integration, mocked transport) ─────────────────────

async def test_ollama_generate_maps_response(monkeypatch):
    prov = OllamaProvider(model="gemma4:e2b")

    async def fake_generate(prompt, system, temperature, max_tokens, use_cache, images=None):
        return "hasil lokal"

    monkeypatch.setattr(prov._client, "generate", fake_generate)
    resp = await prov.generate("halo", GenerationParams(system="sys"))
    assert isinstance(resp, ProviderResponse)
    assert resp.text == "hasil lokal"
    assert resp.provider == "ollama"
    assert resp.completion_tokens > 0


async def test_ollama_generate_normalises_timeout(monkeypatch):
    prov = OllamaProvider(model="gemma4:e2b")

    async def boom(*a, **k):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(prov._client, "generate", boom)
    from providers.exceptions import ProviderTimeoutError

    with pytest.raises(ProviderTimeoutError):
        await prov.generate("x")


async def test_ollama_stream_yields_chunks_and_done(monkeypatch):
    prov = OllamaProvider(model="gemma4:e2b")

    async def fake_stream(prompt, system, temperature):
        for tok in ["a", "b", "c"]:
            yield tok

    monkeypatch.setattr(prov._client, "stream", fake_stream)
    chunks = [c async for c in prov.stream("x")]
    assert [c.text for c in chunks[:3]] == ["a", "b", "c"]
    assert chunks[-1].done is True


async def test_ollama_health_check(monkeypatch):
    prov = OllamaProvider(model="gemma4:e2b")

    async def ok():
        return {"ollama": "ok"}

    monkeypatch.setattr(prov._client, "health_check", ok)
    assert await prov.health_check() is True


# ─── Cloud providers: unconfigured behaviour ──────────────────────────────────

async def test_openai_requires_key(monkeypatch):
    monkeypatch.setattr("providers.openai_provider.settings.OPENAI_API_KEY", "", raising=False)
    prov = OpenAIProvider(model="gpt-4o", api_key="")
    with pytest.raises(ProviderNotConfiguredError):
        await prov.generate("hi")


async def test_openai_health_check_false_without_key():
    prov = OpenAIProvider(model="gpt-4o", api_key="")
    assert await prov.health_check() is False


async def test_claude_health_check_false_without_key():
    prov = ClaudeProvider(model="claude-sonnet-5", api_key="")
    assert await prov.health_check() is False


async def test_gemini_health_check_false_without_key():
    prov = GeminiProvider(model="gemini-1.5-pro", api_key="")
    assert await prov.health_check() is False


# ─── Cloud provider: successful call with mocked HTTP ─────────────────────────

class _FakeResp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status
        self.text = ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=self)  # type: ignore[arg-type]

    def json(self):
        return self._data


class _FakeAsyncClient:
    """Minimal async context-manager stand-in for httpx.AsyncClient."""

    response_data: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        return _FakeResp(type(self).response_data)


async def test_openai_generate_success(monkeypatch):
    payload = {
        "model": "gpt-4o",
        "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2},
    }

    class Client(_FakeAsyncClient):
        response_data = payload

    monkeypatch.setattr("providers.openai_provider.httpx.AsyncClient", Client)
    prov = OpenAIProvider(model="gpt-4o", api_key="sk-test")
    resp = await prov.generate("hi", GenerationParams(system="s"))
    assert resp.text == "hello"
    assert resp.prompt_tokens == 10
    assert resp.completion_tokens == 2
    assert resp.finish_reason == "stop"


async def test_claude_generate_success(monkeypatch):
    payload = {
        "model": "claude-sonnet-5",
        "content": [{"type": "text", "text": "answer"}],
        "usage": {"input_tokens": 7, "output_tokens": 3},
        "stop_reason": "end_turn",
    }

    class Client(_FakeAsyncClient):
        response_data = payload

    monkeypatch.setattr("providers.claude_provider.httpx.AsyncClient", Client)
    prov = ClaudeProvider(model="claude-sonnet-5", api_key="sk-ant")
    resp = await prov.generate("hi")
    assert resp.text == "answer"
    assert resp.prompt_tokens == 7
    assert resp.completion_tokens == 3


async def test_claude_generate_retries_without_sampling_when_unsupported(monkeypatch):
    """Newer Claude models (e.g. claude-sonnet-5) reject temperature/top_p outright."""
    success_payload = {
        "model": "claude-sonnet-5",
        "content": [{"type": "text", "text": "answer"}],
        "usage": {"input_tokens": 7, "output_tokens": 3},
        "stop_reason": "end_turn",
    }

    class RetryClient(_FakeAsyncClient):
        calls: list = []

        async def post(self, url, headers=None, json=None):
            type(self).calls.append(json)
            if "temperature" in json:
                resp = _FakeResp({}, status=400)
                resp.text = '{"error":{"message":"`temperature` is deprecated for this model."}}'
                return resp
            return _FakeResp(success_payload)

    RetryClient.calls = []
    monkeypatch.setattr("providers.claude_provider.httpx.AsyncClient", RetryClient)
    prov = ClaudeProvider(model="claude-sonnet-5", api_key="sk-ant")
    resp = await prov.generate("hi")

    assert resp.text == "answer"
    assert len(RetryClient.calls) == 2
    assert "temperature" in RetryClient.calls[0] and "top_p" in RetryClient.calls[0]
    assert "temperature" not in RetryClient.calls[1] and "top_p" not in RetryClient.calls[1]


async def test_claude_generate_reraises_other_400_errors(monkeypatch):
    class ErrorClient(_FakeAsyncClient):
        async def post(self, url, headers=None, json=None):
            resp = _FakeResp({}, status=400)
            resp.text = '{"error":{"message":"invalid_request: bad messages format"}}'
            return resp

    monkeypatch.setattr("providers.claude_provider.httpx.AsyncClient", ErrorClient)
    prov = ClaudeProvider(model="claude-sonnet-5", api_key="sk-ant")
    with pytest.raises(ProviderError):
        await prov.generate("hi")


async def test_gemini_generate_success(monkeypatch):
    payload = {
        "candidates": [{"content": {"parts": [{"text": "riset"}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 1},
    }

    class Client(_FakeAsyncClient):
        response_data = payload

    monkeypatch.setattr("providers.gemini_provider.httpx.AsyncClient", Client)
    prov = GeminiProvider(model="gemini-1.5-pro", api_key="g-key")
    resp = await prov.generate("hi")
    assert resp.text == "riset"
    assert resp.prompt_tokens == 5


# ─── Vision (Bab 17.1 role) — image payload shape per provider ────────────────

_PNG_PIXEL = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="


def test_gemini_payload_includes_inline_image_part():
    prov = GeminiProvider(model="gemini-1.5-pro", api_key="g-key")
    params = GenerationParams(images=(ImageInput(data=_PNG_PIXEL, mime_type="image/png"),))
    payload = prov._payload("apa ini?", params)
    parts = payload["contents"][0]["parts"]
    assert parts[0] == {"text": "apa ini?"}
    assert parts[1] == {"inline_data": {"mime_type": "image/png", "data": _PNG_PIXEL}}


def test_openai_messages_use_content_parts_when_images_present():
    prov = OpenAIProvider(model="gpt-4o", api_key="k")
    params = GenerationParams(images=(ImageInput(data=_PNG_PIXEL, mime_type="image/png"),))
    messages = prov._messages("apa ini?", params)
    user_msg = messages[-1]
    assert user_msg["role"] == "user"
    assert user_msg["content"][0] == {"type": "text", "text": "apa ini?"}
    assert user_msg["content"][1] == {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{_PNG_PIXEL}"},
    }


def test_openai_messages_stay_plain_string_without_images():
    prov = OpenAIProvider(model="gpt-4o", api_key="k")
    messages = prov._messages("apa ini?", GenerationParams())
    assert messages[-1] == {"role": "user", "content": "apa ini?"}


def test_claude_content_puts_image_blocks_before_text():
    prov = ClaudeProvider(model="claude-sonnet-5", api_key="k")
    params = GenerationParams(images=(ImageInput(data=_PNG_PIXEL, mime_type="image/png"),))
    content = prov._content("apa ini?", params)
    assert content[0] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": _PNG_PIXEL},
    }
    assert content[1] == {"type": "text", "text": "apa ini?"}


def test_claude_content_stays_plain_string_without_images():
    prov = ClaudeProvider(model="claude-sonnet-5", api_key="k")
    assert prov._content("apa ini?", GenerationParams()) == "apa ini?"


async def test_ollama_generate_forwards_images_to_client(monkeypatch):
    prov = OllamaProvider(model="gemma4:e2b")
    captured = {}

    async def fake_generate(prompt, system, temperature, max_tokens, use_cache, images=None):
        captured["images"] = images
        return "ini gambar apa"

    monkeypatch.setattr(prov._client, "generate", fake_generate)
    params = GenerationParams(images=(ImageInput(data=_PNG_PIXEL, mime_type="image/png"),))
    resp = await prov.generate("apa ini?", params)
    assert resp.text == "ini gambar apa"
    assert captured["images"] == [_PNG_PIXEL]


async def test_ollama_generate_passes_none_images_when_absent(monkeypatch):
    prov = OllamaProvider(model="gemma4:e2b")
    captured = {}

    async def fake_generate(prompt, system, temperature, max_tokens, use_cache, images=None):
        captured["images"] = images
        return "ok"

    monkeypatch.setattr(prov._client, "generate", fake_generate)
    await prov.generate("halo", GenerationParams())
    assert captured["images"] is None


# ─── Factory ──────────────────────────────────────────────────────────────────

def test_create_provider_returns_correct_class():
    assert isinstance(create_provider("ollama"), OllamaProvider)
    assert isinstance(create_provider("openai"), OpenAIProvider)
    assert isinstance(create_provider("claude"), ClaudeProvider)
    assert isinstance(create_provider("gemini"), GeminiProvider)


def test_create_provider_unknown_raises():
    with pytest.raises(UnknownProviderError):
        create_provider("does-not-exist")


def test_created_provider_is_base_provider():
    assert isinstance(create_provider("ollama"), BaseProvider)
