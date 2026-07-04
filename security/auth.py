"""Authentication (MASTER_INSTRUCTION.md Bab 30, 58) — API-key principal lookup.

A minimal, dependency-free (Bab 45.3) scheme matching this deployment's
actual maturity: a comma-separated allowlist in ``API_KEYS`` (``key`` or
``key:role``), read once per call from ``api/config.py`` — the one place
that needs to know where secrets come from (Bab 58.3), ready to swap for
Docker/Kubernetes Secrets/Vault later without this module changing.

Not wired into any existing route — every current endpoint stays open
exactly as before (Bab 45, no big rewrite of already-shipped behavior
without an explicit request). ``get_current_principal`` is ready for a
route that opts in via ``Depends``.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass(frozen=True)
class Principal:
    """An authenticated (or, when auth is disabled, default) caller."""

    api_key: str
    role: str = "user"


def _key_roles() -> dict[str, str]:
    from api.config import settings

    roles: dict[str, str] = {}
    for entry in settings.API_KEYS.split(","):
        entry = entry.strip()
        if not entry:
            continue
        key, _, role = entry.partition(":")
        roles[key.strip()] = (role or "user").strip()
    return roles


def verify_api_key(api_key: str) -> Principal | None:
    """Look up ``api_key`` against the configured allowlist; ``None`` if invalid."""
    roles = _key_roles()
    if api_key in roles:
        return Principal(api_key=api_key, role=roles[api_key])
    return None


async def get_current_principal(api_key: str | None = Security(_api_key_header)) -> Principal:
    """FastAPI dependency: the authenticated caller.

    If ``API_KEYS`` is blank (dev default), authentication is disabled and a
    default admin :class:`Principal` is returned so routes that opt into
    this dependency keep working without any setup. Once ``API_KEYS`` is
    set, a missing/invalid key raises 401.
    """
    from api.config import settings

    if not settings.API_KEYS.strip():
        return Principal(api_key="", role="admin")

    principal = verify_api_key(api_key or "")
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid or missing API key")
    return principal
