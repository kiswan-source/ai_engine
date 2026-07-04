"""Summary Memory — rolling summaries of long conversations/documents (Bab 22).

Exists to relieve the context window (Bab 50.3): instead of replaying a whole
history into a prompt, agents fetch the stored summary. Summarisation itself is
delegated to an injected async ``summarizer`` callable; by default it resolves
the ``memory`` role's provider (Bab 20) lazily — tests inject a stub instead.
"""
from __future__ import annotations

from typing import Awaitable, Callable

from core.utils.logger import get_logger

from .stores import HashStore

logger = get_logger(__name__)

Summarizer = Callable[[str], Awaitable[str]]

_SUMMARY_FIELD = "summary"
_DEFAULT_PROMPT = (
    "Ringkas teks berikut menjadi paragraf padat yang mempertahankan semua fakta, "
    "angka, nama, dan keputusan penting. Jawab hanya dengan ringkasannya.\n\n{text}"
)


async def _default_summarizer(text: str) -> str:
    """Summarise via the ``memory`` role's provider (local Ollama by default)."""
    from providers import GenerationParams, create_for_role

    provider = create_for_role("memory")
    resp = await provider.generate(
        _DEFAULT_PROMPT.format(text=text),
        GenerationParams(temperature=0.3, max_tokens=1024),
    )
    return resp.text.strip()


class SummaryMemory:
    """Store and refresh one summary per scope (session id, document id, …)."""

    def __init__(self, store: HashStore, summarizer: Summarizer | None = None) -> None:
        self._store = store
        self._summarizer = summarizer or _default_summarizer

    async def save_summary(self, scope: str, summary: str) -> None:
        await self._store.set_field(scope, _SUMMARY_FIELD, summary)

    async def get_summary(self, scope: str) -> str | None:
        return await self._store.get_field(scope, _SUMMARY_FIELD)

    async def summarize_and_store(self, scope: str, text: str) -> str:
        """Summarise ``text`` (folding in any existing summary) and persist it.

        Raises:
            ProviderError: If the summariser's provider call fails; the caller
                decides whether a missing summary is fatal (usually it is not).
        """
        previous = await self.get_summary(scope)
        source = f"Ringkasan sebelumnya:\n{previous}\n\nLanjutan:\n{text}" if previous else text
        summary = await self._summarizer(source)
        await self.save_summary(scope, summary)
        logger.info("summary_memory.updated", scope=scope, chars=len(summary))
        return summary

    async def clear(self, scope: str) -> None:
        await self._store.delete(scope)
