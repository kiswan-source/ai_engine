"""Unit tests for the Workspace Delete Gate (Workspace Slice 2, Fase 12)."""
import time

import pytest

from memory.stores import InMemoryHashStore, RedisHashStore
from workspace.delete_gate import (
    DeleteRequest,
    WorkspaceDeleteGate,
    _default_store,
    get_shared_delete_gate,
)


class FakeAsyncRedis:
    """Minimal async stand-in for redis.asyncio.Redis (hash ops only) —
    same fixture shape test_approval.py already uses for HumanApprovalGate."""

    def __init__(self):
        self.hashes = {}

    async def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def hdel(self, key, field):
        self.hashes.get(key, {}).pop(field, None)

    async def delete(self, key):
        self.hashes.pop(key, None)

    async def expire(self, key, ttl):
        pass


async def test_request_creates_pending_unconfirmed_token():
    gate = WorkspaceDeleteGate()
    req = await gate.request("ws1", "f1", "docs/report.txt", requested_by="alice")
    assert req.token
    assert not req.decided
    assert req.confirmed is None
    fetched = await gate.get(req.token)
    assert fetched == req


async def test_confirm_marks_decided_and_records_approver():
    gate = WorkspaceDeleteGate()
    req = await gate.request("ws1", "f1", "docs/report.txt", requested_by="alice")
    decided = await gate.confirm(req.token, decided_by="alice", reason="tidak dipakai lagi")
    assert decided.decided
    assert decided.confirmed is True
    assert decided.decided_by == "alice"
    assert decided.reason == "tidak dipakai lagi"


async def test_confirm_unknown_token_raises_keyerror():
    gate = WorkspaceDeleteGate()
    with pytest.raises(KeyError):
        await gate.confirm("does-not-exist", decided_by="alice")


async def test_confirm_twice_raises_valueerror():
    """A token is single-use — reusing it (accidental double-submit, or a
    replay) must never delete twice."""
    gate = WorkspaceDeleteGate()
    req = await gate.request("ws1", "f1", "docs/report.txt", requested_by="alice")
    await gate.confirm(req.token, decided_by="alice")
    with pytest.raises(ValueError):
        await gate.confirm(req.token, decided_by="alice")


async def test_confirm_expired_token_raises_valueerror():
    gate = WorkspaceDeleteGate(ttl_seconds=0)
    req = await gate.request("ws1", "f1", "docs/report.txt", requested_by="alice")
    time.sleep(0.01)
    assert req.expired
    with pytest.raises(ValueError):
        await gate.confirm(req.token, decided_by="alice")


async def test_get_returns_none_for_unknown_token():
    gate = WorkspaceDeleteGate()
    assert await gate.get("missing") is None


async def test_delete_request_expired_property_false_before_ttl():
    req = DeleteRequest(
        token="t", workspace_id="w", folder_id="f", relative_path="a.txt",
        requested_by="alice", ttl_seconds=3600,
    )
    assert not req.expired


async def test_delete_request_expired_property_false_once_decided():
    """A decided request is never 'expired' — expiry only matters for
    still-pending tokens; a resolved one is just history."""
    req = DeleteRequest(
        token="t", workspace_id="w", folder_id="f", relative_path="a.txt",
        requested_by="alice", ttl_seconds=0, decided=True,
    )
    assert not req.expired


# ─── statelessness (same Bab 38 rule 1 pattern as HumanApprovalGate) ──────

async def test_default_store_is_in_memory_by_default(monkeypatch):
    monkeypatch.setattr("api.config.settings.APPROVAL_STATE_BACKEND", "memory")
    assert isinstance(_default_store(), InMemoryHashStore)


async def test_default_store_is_redis_when_configured(monkeypatch):
    monkeypatch.setattr("api.config.settings.APPROVAL_STATE_BACKEND", "redis")
    assert isinstance(_default_store(), RedisHashStore)


async def test_redis_backed_gate_shares_state_across_instances():
    """Two WorkspaceDeleteGate instances over the same Redis backend must
    see each other's writes — the delete-request and delete-confirm HTTP
    calls are two separate requests, so this must hold even without the
    process-wide singleton for a horizontally-scaled deployment."""
    fake = FakeAsyncRedis()
    gate1 = WorkspaceDeleteGate(store=RedisHashStore("delete-test", client=fake))
    req = await gate1.request("ws1", "f1", "docs/report.txt", requested_by="alice")

    gate2 = WorkspaceDeleteGate(store=RedisHashStore("delete-test", client=fake))
    fetched = await gate2.get(req.token)
    assert fetched.relative_path == "docs/report.txt"

    await gate2.confirm(req.token, decided_by="alice")
    # gate1 must see the decision made via gate2 — same underlying store.
    reloaded = await gate1.get(req.token)
    assert reloaded.decided


def test_get_shared_delete_gate_returns_same_instance():
    """The process-wide singleton — without it, delete-request and
    delete-confirm (two separate HTTP calls) would each get a fresh
    WorkspaceDeleteGate with its own InMemoryHashStore, losing every
    pending token between them for the in-memory (dev/CI default) backend."""
    assert get_shared_delete_gate() is get_shared_delete_gate()
