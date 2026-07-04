"""Unit tests for the Shared Memory tiers (Bab 22) — no Redis/Postgres (Bab 12.3)."""
import types

import pytest

from memory import (
    ConversationMemory,
    LongTermMemory,
    ReflectionMemory,
    SummaryMemory,
    VectorMemory,
    WorkingMemory,
    build_memory_manager,
)
from memory.conversation_memory import InMemoryConversationStore
from memory.long_term_memory import InMemoryLongTermStore
from memory.stores import (
    InMemoryHashStore,
    InMemoryListStore,
    RedisHashStore,
    RedisListStore,
)


# ─── Test doubles ─────────────────────────────────────────────────────────────

class FakeAsyncRedis:
    """Minimal async stand-in for redis.asyncio.Redis (hash + list ops)."""

    def __init__(self):
        self.hashes = {}
        self.lists = {}
        self.expirations = {}

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
        self.lists.pop(key, None)

    async def expire(self, key, ttl):
        self.expirations[key] = ttl

    async def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def _slice(self, key, start, end):
        items = self.lists.get(key, [])
        n = len(items)
        if start < 0:
            start = max(start + n, 0)
        if end < 0:
            end += n
        return items[start : end + 1]

    async def lrange(self, key, start, end):
        return self._slice(key, start, end)

    async def ltrim(self, key, start, end):
        self.lists[key] = self._slice(key, start, end)


# ─── Working Memory ──────────────────────────────────────────────────────────

async def test_working_memory_roundtrip_and_clear():
    wm = WorkingMemory(InMemoryHashStore(), ttl=60)
    await wm.set("trace-1", "step", {"n": 1, "ok": True})
    await wm.set("trace-1", "note", "halo")
    assert await wm.get("trace-1", "step") == {"n": 1, "ok": True}
    assert await wm.get_all("trace-1") == {"step": {"n": 1, "ok": True}, "note": "halo"}
    assert await wm.get("trace-2", "step", default="x") == "x"  # scope isolation
    await wm.forget("trace-1", "note")
    assert await wm.get("trace-1", "note") is None
    await wm.clear("trace-1")
    assert await wm.get_all("trace-1") == {}


async def test_inmemory_hash_store_ttl_expires(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(
        "memory.stores.time", types.SimpleNamespace(monotonic=lambda: now[0])
    )
    store = InMemoryHashStore()
    await store.set_field("scope", "k", "v", ttl=10)
    assert await store.get_field("scope", "k") == "v"
    now[0] = 11.0  # past the TTL
    assert await store.get_field("scope", "k") is None


# ─── Conversation Memory ─────────────────────────────────────────────────────

async def test_conversation_memory_history_order_and_limit():
    cm = ConversationMemory(InMemoryConversationStore())
    await cm.add_message("s1", "user", "halo")
    await cm.add_message("s1", "assistant", "hai, ada yang bisa dibantu?")
    await cm.add_message("s1", "user", "hitung luas WIUP")
    history = await cm.get_history("s1", limit=2)
    assert [m["content"] for m in history] == ["hai, ada yang bisa dibantu?", "hitung luas WIUP"]
    chat = await cm.as_chat_messages("s1")
    assert chat[0] == {"role": "user", "content": "halo"}
    await cm.clear("s1")
    assert await cm.get_history("s1") == []


# ─── Summary Memory ──────────────────────────────────────────────────────────

async def test_summary_memory_folds_previous_summary():
    calls = []

    async def stub_summarizer(text):
        calls.append(text)
        return f"RINGKASAN({len(calls)})"

    sm = SummaryMemory(InMemoryHashStore(), summarizer=stub_summarizer)
    assert await sm.get_summary("s1") is None
    await sm.summarize_and_store("s1", "teks panjang pertama")
    result = await sm.summarize_and_store("s1", "lanjutan diskusi")
    assert result == "RINGKASAN(2)"
    assert await sm.get_summary("s1") == "RINGKASAN(2)"
    # The second call must fold in the first summary, not restart from scratch.
    assert "RINGKASAN(1)" in calls[1] and "lanjutan diskusi" in calls[1]


# ─── Long-Term Memory ────────────────────────────────────────────────────────

async def test_long_term_memory_namespaced_facts():
    ltm = LongTermMemory(InMemoryLongTermStore())
    await ltm.remember("user:kiswan", "bahasa", "id")
    await ltm.remember("user:kiswan", "model_favorit", "qwen2.5:3b")
    await ltm.remember("project:ai_engine", "tahap", 3)
    assert await ltm.recall("user:kiswan", "bahasa") == "id"
    assert await ltm.recall_all("user:kiswan") == {"bahasa": "id", "model_favorit": "qwen2.5:3b"}
    assert await ltm.recall("project:ai_engine", "bahasa") is None  # isolated
    await ltm.forget("user:kiswan", "bahasa")
    assert await ltm.recall("user:kiswan", "bahasa") is None


# ─── Vector Memory ───────────────────────────────────────────────────────────

async def test_vector_memory_ranks_relevant_text_first():
    vm = VectorMemory()
    await vm.add("harga nikel dunia naik tajam", metadata={"doc": "nikel"})
    await vm.add("peta wilayah tambang format kml", metadata={"doc": "gis"})
    hits = await vm.search("berapa harga nikel sekarang", top_k=2)
    assert hits[0].metadata["doc"] == "nikel"
    assert hits[0].score > hits[1].score


async def test_vector_memory_min_score_and_clear():
    vm = VectorMemory()
    await vm.add("dokumen wiup batubara")
    assert await vm.search("zzz qqq xxx", min_score=0.9) == []
    assert await vm.count() == 1
    await vm.clear()
    assert await vm.count() == 0
    assert await vm.search("apa saja") == []


# ─── Reflection Memory ───────────────────────────────────────────────────────

async def test_reflection_memory_records_and_caps_entries():
    rm = ReflectionMemory(InMemoryListStore(), max_entries=3)
    for i in range(5):
        await rm.record(
            "writer", task_id=f"t{i}", trace_id="tr", success=i % 2 == 0,
            lesson=f"pelajaran-{i}" if i >= 3 else "",
        )
    recent = await rm.recent("writer", limit=10)
    assert len(recent) == 3  # capped to max_entries
    assert [e["task_id"] for e in recent] == ["t2", "t3", "t4"]
    assert await rm.lessons_for("writer") == ["pelajaran-3", "pelajaran-4"]


# ─── Redis-backed stores (fake client) ───────────────────────────────────────

async def test_redis_hash_store_with_fake_client():
    fake = FakeAsyncRedis()
    store = RedisHashStore("working", client=fake)
    await store.set_field("trace-1", "k", "v", ttl=30)
    assert await store.get_field("trace-1", "k") == "v"
    assert fake.expirations == {"mem:working:trace-1": 30}
    assert await store.get_all("trace-1") == {"k": "v"}
    await store.delete("trace-1")
    assert await store.get_all("trace-1") == {}


async def test_redis_list_store_with_fake_client():
    fake = FakeAsyncRedis()
    store = RedisListStore("reflection", client=fake)
    for i in range(4):
        await store.append("writer", f"e{i}", max_len=3)
    assert await store.last("writer", 10) == ["e1", "e2", "e3"]
    assert await store.last("writer", 2) == ["e2", "e3"]


# ─── Memory Manager ──────────────────────────────────────────────────────────

async def test_build_memory_manager_default_is_service_free():
    mm = build_memory_manager()  # defaults: memory/memory — must not touch services
    await mm.working.set("tr", "k", 1)
    assert await mm.working.get("tr", "k") == 1
    await mm.conversation.add_message("s", "user", "halo")
    assert len(await mm.conversation.get_history("s")) == 1
    await mm.long_term.remember("ns", "k", "v")
    assert await mm.long_term.recall("ns", "k") == "v"
    await mm.reflection.record("writer", "t1", "tr", True)
    assert len(await mm.reflection.recent("writer")) == 1
