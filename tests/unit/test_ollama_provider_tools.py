"""Fase 14 (DCF v5 mandate — orchestrator agent tool access): the native
tool-calling round-loop `OllamaProvider._generate_with_tools` is the actual
mechanism agents/generic_agent.py's EXECUTOR sub-loop relies on — this is
where Ollama's real `/api/chat` shape gets exercised, not just the calling
code around it. No live Ollama call (Bab 12.3) — a fake httpx.AsyncClient
stands in, same pattern tests/unit/test_providers.py already uses for the
other three providers.
"""
import pytest

from providers.base_provider import GenerationParams
from providers.exceptions import ProviderResponseError
from providers.ollama_provider import OllamaProvider


class _FakeChatResp:
    def __init__(self, data: dict, status: int = 200):
        self._data = data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("err", request=None, response=self)  # type: ignore[arg-type]

    def json(self):
        return self._data


class _RoundsClient:
    """Returns one canned `/api/chat` response per call, in order."""

    responses: list = []
    calls: list = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None):
        type(self).calls.append(json)
        idx = len(type(self).calls) - 1
        return _FakeChatResp(type(self).responses[idx])


TOOL_SCHEMA = ({"type": "function", "function": {"name": "read_pdf", "description": "", "parameters": {}}},)


async def test_payload_includes_num_ctx(monkeypatch):
    """Fase 15 fix: this call used to omit num_ctx entirely, silently
    falling back to Ollama's 4096-token default instead of
    settings.OLLAMA_NUM_CTX (16384) — every EXECUTOR tool-calling round in
    Fase 14 was running at the wrong context size until this was caught."""
    from api.config import settings

    round1 = {"message": {"role": "assistant", "content": "ok"}}

    class Client(_RoundsClient):
        responses = [round1]
        calls = []

    monkeypatch.setattr("providers.ollama_provider.httpx.AsyncClient", Client)

    async def executor(name, args):  # pragma: no cover
        raise AssertionError("not needed for this test")

    provider = OllamaProvider(model="gemma4:e2b")
    params = GenerationParams(tools=TOOL_SCHEMA, tool_executor=executor)
    await provider.generate("Halo", params)

    assert Client.calls[0]["options"]["num_ctx"] == settings.OLLAMA_NUM_CTX


async def test_executes_tool_call_and_returns_final_text(monkeypatch):
    round1 = {"message": {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "read_pdf", "arguments": {"file_path": "a.pdf"}}}
    ]}}
    round2 = {"message": {"role": "assistant", "content": "Ringkasan dokumen selesai."}}

    class Client(_RoundsClient):
        responses = [round1, round2]
        calls = []

    monkeypatch.setattr("providers.ollama_provider.httpx.AsyncClient", Client)

    calls_made = []

    async def executor(name, args):
        calls_made.append((name, args))
        return {"success": True, "file": "/reports/a_summary.pdf", "text": "isi"}

    provider = OllamaProvider(model="gemma4:e2b")
    params = GenerationParams(tools=TOOL_SCHEMA, tool_executor=executor)
    resp = await provider.generate("Ringkas a.pdf", params)

    assert resp.text == "Ringkasan dokumen selesai."
    assert calls_made == [("read_pdf", {"file_path": "a.pdf"})]
    assert resp.tool_calls_made == (
        {"name": "read_pdf", "args": {"file_path": "a.pdf"}, "success": True, "file": "/reports/a_summary.pdf"},
    )
    # Two full /api/chat rounds: one that returned tool_calls, one that didn't.
    assert len(Client.calls) == 2


async def test_no_tool_calls_returns_immediately_after_one_round(monkeypatch):
    round1 = {"message": {"role": "assistant", "content": "Tidak perlu tool."}}

    class Client(_RoundsClient):
        responses = [round1]
        calls = []

    monkeypatch.setattr("providers.ollama_provider.httpx.AsyncClient", Client)

    async def executor(name, args):  # pragma: no cover - must never be called
        raise AssertionError("tool_executor should not be invoked")

    provider = OllamaProvider(model="gemma4:e2b")
    params = GenerationParams(tools=TOOL_SCHEMA, tool_executor=executor)
    resp = await provider.generate("Halo", params)

    assert resp.text == "Tidak perlu tool."
    assert resp.tool_calls_made == ()
    assert len(Client.calls) == 1


async def test_round_loop_stops_at_max_rounds_without_crashing(monkeypatch):
    """A model that keeps emitting tool_calls forever must not hang the
    agent — the loop is bounded, and simply returns the last content once
    exhausted (matches core/chat/engine.py's MAX_TOOL_ROUNDS posture)."""
    always_tool_calls = {"message": {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "read_pdf", "arguments": {"file_path": "a.pdf"}}}
    ]}}

    class Client(_RoundsClient):
        responses = [always_tool_calls] * 10  # more than _MAX_TOOL_ROUNDS
        calls = []

    monkeypatch.setattr("providers.ollama_provider.httpx.AsyncClient", Client)

    async def executor(name, args):
        return {"success": True}

    provider = OllamaProvider(model="gemma4:e2b")
    params = GenerationParams(tools=TOOL_SCHEMA, tool_executor=executor)
    resp = await provider.generate("Halo", params)

    from providers.ollama_provider import _MAX_TOOL_ROUNDS

    assert len(Client.calls) == _MAX_TOOL_ROUNDS
    assert len(resp.tool_calls_made) == _MAX_TOOL_ROUNDS


async def test_tool_executor_exception_is_recorded_not_raised(monkeypatch):
    round1 = {"message": {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "read_pdf", "arguments": {"file_path": "missing.pdf"}}}
    ]}}
    round2 = {"message": {"role": "assistant", "content": "File tidak ditemukan, maaf."}}

    class Client(_RoundsClient):
        responses = [round1, round2]
        calls = []

    monkeypatch.setattr("providers.ollama_provider.httpx.AsyncClient", Client)

    async def executor(name, args):
        raise RuntimeError("boom")

    provider = OllamaProvider(model="gemma4:e2b")
    params = GenerationParams(tools=TOOL_SCHEMA, tool_executor=executor)
    resp = await provider.generate("Ringkas missing.pdf", params)

    assert resp.text == "File tidak ditemukan, maaf."
    assert resp.tool_calls_made[0]["success"] is False


async def test_http_error_raises_provider_response_error(monkeypatch):
    class Client(_RoundsClient):
        responses = [{}]
        calls = []

        async def post(self, url, json=None):
            return _FakeChatResp({}, status=500)

    monkeypatch.setattr("providers.ollama_provider.httpx.AsyncClient", Client)

    async def executor(name, args):  # pragma: no cover
        raise AssertionError("must not reach the executor")

    provider = OllamaProvider(model="gemma4:e2b")
    params = GenerationParams(tools=TOOL_SCHEMA, tool_executor=executor)
    with pytest.raises(ProviderResponseError):
        await provider.generate("Halo", params)
