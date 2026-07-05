"""Domain event type definitions (MASTER_INSTRUCTION.md Bab 23).

Event names are dotted strings ``<domain>.<state-or-action>``. The agent set
mirrors the Agent Lifecycle states (Bab 48.1) and the workflow set mirrors the
Workflow/Task State Machine (Bab 49.1), so the Event Bus can publish *every*
lifecycle transition (roadmap Tahap 3 exit criteria) without ad-hoc names.
"""
from __future__ import annotations

# ── Agent lifecycle (Bab 48.1) ───────────────────────────────────────────────
AGENT_CREATED = "agent.created"
AGENT_REGISTERED = "agent.registered"
AGENT_READY = "agent.ready"
AGENT_IDLE = "agent.idle"
AGENT_ASSIGNED = "agent.assigned"
AGENT_RUNNING = "agent.running"
AGENT_WAITING = "agent.waiting"
AGENT_REVIEWING = "agent.reviewing"
AGENT_COMPLETED = "agent.completed"
AGENT_FAILED = "agent.failed"
AGENT_RETRY = "agent.retry"
AGENT_ARCHIVED = "agent.archived"

# ── Workflow / task state machine (Bab 49.1) ────────────────────────────────
WORKFLOW_PENDING = "workflow.pending"
WORKFLOW_PLANNING = "workflow.planning"
WORKFLOW_RESEARCH = "workflow.research"
WORKFLOW_EXECUTING = "workflow.executing"
WORKFLOW_REVIEWING = "workflow.reviewing"
WORKFLOW_APPROVED = "workflow.approved"
WORKFLOW_COMPLETED = "workflow.completed"
WORKFLOW_CANCELLED = "workflow.cancelled"
WORKFLOW_FAILED = "workflow.failed"
WORKFLOW_RETRY = "workflow.retry"
WORKFLOW_ROLLBACK = "workflow.rollback"

# ── Other domains (Bab 23 prinsip 1) ────────────────────────────────────────
CONSENSUS_DECIDED = "consensus.decided"  # Bab 26 — wired in Tahap 4
MEMORY_WRITTEN = "memory.written"  # Bab 22 — optional observability hook

# ── Circuit Breaker (Bab 55) — mirrors the Bab 55.2 state diagram ───────────
CIRCUIT_OPENED = "circuit.opened"
CIRCUIT_HALF_OPEN = "circuit.half_open"
CIRCUIT_CLOSED = "circuit.closed"


def agent_event(state: str) -> str:
    """Event name for an agent lifecycle state, e.g. ``running`` → ``agent.running``."""
    return f"agent.{state.lower()}"


def workflow_event(state: str) -> str:
    """Event name for a workflow/task state, e.g. ``executing`` → ``workflow.executing``."""
    return f"workflow.{state.lower()}"
