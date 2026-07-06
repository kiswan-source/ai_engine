"""Orchestrator API — exposes the multi-agent workflow system (`orchestrator/`,
`agents/`, `workflows/`) to HTTP, for the web UI's Multi-Agent panel.

Not a protected folder (Bab 45.1 lists `core/chat/`, `agent/tools/`,
`api/routes/chat.py`, `core/document/`, `core/gis/` — this file is none of
those), so it's a plain new router rather than a strangler-pattern change.

One module-level ``Orchestrator`` is reused across requests (like
``providers.circuit_breaker.breakers``) so a pending Human Approval request
from one ``/run`` call is still there for a later ``/approvals/*`` call in
the same process — a fresh instance per request would reset the in-memory
``TaskManager``/``HumanApprovalGate`` state (irrelevant when
``APPROVAL_STATE_BACKEND=redis``, but this keeps the default `memory` backend
usable too).
"""
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from orchestrator.orchestrator import Orchestrator
from registry.model_registry import ROLES
from security.auth import Principal, get_current_principal
from core.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

_orchestrator = Orchestrator()


class WorkflowRunRequest(BaseModel):
    prompt: str
    roles: list[str]
    mode: str = "sequential"
    system: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048
    # Vision (Bab 17.1 role): data: URI strings, exactly what a browser's
    # FileReader.readAsDataURL() produces — no extra encoding step needed on
    # the frontend. Parsed into {"data", "mime_type"} dicts before reaching
    # the Orchestrator, which knows nothing about the wire format.
    images: list[str] = []
    # Simulation Mode (Bab 68 Backlog Prioritas 16, Tahap 36) — dry-run this
    # workflow through providers.mock_provider.MockProvider instead of real
    # vendor calls, for validating routing/sequencing on a complex workflow
    # without cost before running it for real.
    simulate: bool = False


def _parse_data_uri(uri: str) -> dict[str, str]:
    """``data:image/png;base64,AAAA...`` -> ``{"mime_type": "image/png", "data": "AAAA..."}``."""
    if not uri.startswith("data:") or ";base64," not in uri:
        raise HTTPException(status_code=400, detail="images must be data: URIs with base64 encoding")
    header, data = uri.split(",", 1)
    mime_type = header[len("data:") : -len(";base64")]
    return {"mime_type": mime_type, "data": data}


class ApprovalDecisionRequest(BaseModel):
    approved: bool
    decided_by: str
    reason: str = ""


@router.get("/roles")
async def list_roles():
    """Canonical agent roles (Bab 17.1) available to build a workflow from."""
    return {"roles": list(ROLES)}


@router.get("/modes")
async def list_modes():
    """Workflow patterns selectable for `/run` (Bab 24)."""
    from workflows import WORKFLOWS

    return {"modes": list(WORKFLOWS.keys())}


@router.post("/run")
async def run_workflow(req: WorkflowRunRequest):
    if not req.roles:
        raise HTTPException(status_code=400, detail="roles must not be empty")
    images = [_parse_data_uri(uri) for uri in req.images]
    try:
        result = await _orchestrator.run(
            prompt=req.prompt,
            roles=req.roles,
            mode=req.mode,
            system=req.system,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            images=images or None,
            simulate=req.simulate,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    state = _orchestrator.tasks.state_of(result.trace_id)
    return {**asdict(result), "state": state.value if state else None}


@router.get("/approvals")
async def list_pending_approvals():
    """Human Approval requests still awaiting a decision (Bab 61.3)."""
    pending = await _orchestrator.pending_approvals()
    return {"approvals": [asdict(a) for a in pending]}


@router.post("/approvals/{trace_id}/decide")
async def decide_approval(
    trace_id: str, req: ApprovalDecisionRequest, principal: Principal = Depends(get_current_principal)
):
    try:
        state = await _orchestrator.finalize_approval(
            trace_id, approved=req.approved, decided_by=req.decided_by, reason=req.reason, role=principal.role
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no pending approval for trace_id {trace_id!r}")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {"trace_id": trace_id, "state": state.value}
