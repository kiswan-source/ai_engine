"""Chat -> Orchestrator bridge (Fase 6, DCF v5 mandate "Cowork Experience").

Lets a Chat Engine turn trigger the full multi-agent flow (plan -> pick
agent(s) -> run workflow -> validate -> escalate to Human Approval if
needed -> output) the mandate's example dialog describes — WITHOUT a new
SSE protocol or inline chat approval UI. The model calls
``run_orchestrated_workflow`` like any other tool (existing tool-calling
loop, existing infrastructure) when it judges a request needs real
planning/multi-agent work rather than a single tool call; the result
surfaces as one tool_result card in the chat UI, same rendering pattern
every other tool already uses.

If the run escalates to Human Approval, this does NOT wait inline — the
result just says so, with the `trace_id` a human uses on the EXISTING
Approval page (`/api/v1/orchestrator/approvals/*`, `ApprovalPage.tsx`) to
decide. Building a live pause-and-confirm inside a chat turn was
considered and explicitly rejected for this pass (see the Fase 6 design
decision) — reusing the page that already does this is smaller and safer
than inventing an in-chat equivalent.

Uses `orchestrator.orchestrator.get_shared_orchestrator()` — the SAME
instance `api/routes/orchestrator.py` uses — so a pending approval this
tool opens is visible to that page's `_orchestrator.pending_approvals()`
for the in-memory (dev/CI default) state backends. Runs via `asyncio.run()`
inside a worker thread (`ToolRegistry.execute` -> `asyncio.to_thread`, the
same bridge every other async tool in this package uses) — verified
against the default in-memory `TASK_STATE_BACKEND`/`APPROVAL_STATE_BACKEND`/
`MESSAGE_BROKER`; a Redis-backed deployment reusing the same shared
orchestrator across the main event loop (API requests) and this tool's
separate per-call loop hasn't been verified and may hit the same
event-loop-affinity class of issue `agent/tools/workspace_reader.py` and
`agent/tools/memory_tools.py` already document for Postgres.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from agents.base_agent import AgentResult


def _step_summary(results: List[AgentResult]) -> List[Dict[str, Any]]:
    return [
        {"role": r.role, "agent_id": r.agent_id, "output": r.output,
         "confidence": r.confidence, "ok": r.ok}
        for r in results
    ]


def run_orchestrated_workflow(
    goal: str, roles: List[str], mode: str = "sequential",
) -> Dict[str, Any]:
    """Run a full multi-agent workflow (plan -> agent(s) -> validate ->
    escalate-if-needed) for ``goal`` and return a structured summary — not
    a live stream, one result once the run settles (or escalates)."""

    async def _run() -> Dict[str, Any]:
        from orchestrator.orchestrator import get_shared_orchestrator

        orchestrator = get_shared_orchestrator()
        result = await orchestrator.run(prompt=goal, roles=roles, mode=mode)
        state = orchestrator.tasks.state_of(result.trace_id)
        return {
            "success": not result.failed,
            "final_output": result.final_output,
            "steps": _step_summary(result.results),
            "mode": result.mode,
            "trace_id": result.trace_id,
            "state": state.value if state else None,
            "degraded": result.degraded,
            "escalate": result.escalate,
            "message": (
                f"Alur kerja ini butuh persetujuan manusia sebelum selesai "
                f"(trace_id={result.trace_id}). Buka halaman Approval untuk memutuskan."
                if result.escalate else None
            ),
        }

    return asyncio.run(_run())
