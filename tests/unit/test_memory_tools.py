"""Unit tests for cross-session memory tools (Fase 3, R-08 sibling —
DCF v5 mandate "Memory Intelligence Evolution"). In-memory backend only
(MEMORY_PERSISTENT_BACKEND default) — the Postgres branch needs a real
database, exercised by hand per the module's own docstring, not here."""
import pytest

from agent.tools.memory_tools import recall_facts, remember_fact
from memory.memory_manager import get_shared_memory_manager


def test_remember_then_recall_round_trips():
    remember_fact(key="bahasa_favorit", value="Python", owner="alice")
    result = recall_facts(owner="alice")

    assert result["success"] is True
    assert result["facts"] == {"bahasa_favorit": "Python"}


def test_facts_are_isolated_per_owner():
    remember_fact(key="warna_favorit", value="biru", owner="alice")
    remember_fact(key="warna_favorit", value="merah", owner="bob")

    assert recall_facts(owner="alice")["facts"] == {"warna_favorit": "biru"}
    assert recall_facts(owner="bob")["facts"] == {"warna_favorit": "merah"}


def test_none_owner_falls_back_to_shared_anonymous_namespace():
    remember_fact(key="k", value="v", owner=None)
    assert recall_facts(owner=None)["facts"] == {"k": "v"}


def test_recall_facts_empty_for_owner_with_nothing_remembered():
    assert recall_facts(owner="nobody-ever-called-remember")["facts"] == {}


def test_shares_state_with_the_shared_memory_manager():
    """The in-memory backend must reuse get_shared_memory_manager()'s store —
    otherwise remember_fact/recall_facts would be a disconnected island from
    whatever core/chat/engine.py or api/routes/memory.py see."""
    remember_fact(key="k2", value="v2", owner="carol")

    manager = get_shared_memory_manager()
    import asyncio

    facts = asyncio.run(manager.long_term.recall_all("owner:carol"))
    assert facts == {"k2": "v2"}
