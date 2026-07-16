"""Shared pytest fixtures — global test isolation (Bab 12.3)."""
import pytest


@pytest.fixture(autouse=True)
def _isolated_audit_log(tmp_path, monkeypatch):
    """Every test's security.audit_log writes go to a per-test temp file,
    never the real AUDIT_LOG_PATH in the repo root (Tahap 7 — any test that
    reaches HumanApprovalGate.decide() or a guardrail violation writes one)."""
    monkeypatch.setattr("api.config.settings.AUDIT_LOG_PATH", str(tmp_path / "security_audit.log"))


@pytest.fixture(autouse=True)
def _isolated_circuit_breakers(monkeypatch):
    """Fresh default breaker registry per test (Tahap 9) — any Dispatcher built
    without an explicit registry shares the module-level one, so provider
    failures in one test must not trip breakers seen by the next."""
    from providers import circuit_breaker

    monkeypatch.setattr(circuit_breaker, "breakers", circuit_breaker.CircuitBreakerRegistry())


@pytest.fixture(autouse=True)
def _isolated_shared_memory_manager(monkeypatch):
    """Fresh get_shared_memory_manager() singleton per test (Fase 3) — the
    in-memory dev/CI backends store their actual data on the singleton
    instance itself, so a session_id or owner namespace reused across two
    tests would otherwise see the previous test's writes."""
    from memory import memory_manager

    monkeypatch.setattr(memory_manager, "_shared_manager", None)


@pytest.fixture(autouse=True)
def _isolated_shared_orchestrator(monkeypatch):
    """Fresh get_shared_orchestrator() singleton per test (Fase 6) — same
    reasoning as the memory manager above: TaskManager/HumanApprovalGate
    state lives on the singleton instance for the in-memory default
    backends, so a trace_id or pending approval from one test must not
    leak into the next."""
    from orchestrator import orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module, "_shared_orchestrator", None)
