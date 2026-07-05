"""Plugin API (MASTER_INSTRUCTION.md Bab 59) — a Settings-area toggle for
optional capabilities, not a new sidebar area
(AI_WORKSPACE_ARCHITECTURE.md §8: "Area Settings harus memiliki ruang untuk
mengaktifkan/menonaktifkan kapabilitas tambahan (integrasi baru) tanpa
perubahan navigasi inti").

Listing is open (matches monitoring.py/knowledge.py's current posture);
toggling is gated to ``manage_plugins`` (admin-only by default, since the
role matrix's only holder of "*" is "admin") — the first real usage of
``security.permissions.require_role``, which existed since Tahap 7 but had
no caller yet.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from registry import plugin_registry
from security.auth import Principal, get_current_principal
from security.permissions import require_role

router = APIRouter()


class PluginToggleRequest(BaseModel):
    enabled: bool


@router.get("")
async def list_plugins(principal: Principal = Depends(get_current_principal)):
    return {"plugins": plugin_registry.list_plugins()}


@router.patch("/{name}")
async def toggle_plugin(
    name: str,
    body: PluginToggleRequest,
    principal: Principal = Depends(require_role("manage_plugins")),
):
    result = plugin_registry.set_enabled(name, body.enabled)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    return result
