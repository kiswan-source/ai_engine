"""Endpoint location classification (Fase 1, SEC-4 —
DCF_SECURITY_AUDIT_2026-07-11.md temuan #4).

Bab 30's PII redaction rule is "sebelum dikirim ke provider eksternal" —
before data leaves this deployment's own infrastructure. Until this Tahap,
that boundary was decided by checking the provider's *name*
(`agents/generic_agent.py`: skip redaction when ``provider.name == "ollama"``)
rather than where the endpoint actually is. That's wrong on two live
deployment modes at once: Docker Compose's Ollama endpoint is the WSL host's
virtual-network IP (not a loopback literal), and the Kubernetes manifest set
lets `OLLAMA_BASE_URL` point anywhere, including a genuinely external host —
neither is "local" just because the provider is named "ollama".

:func:`is_internal_endpoint` replaces the name check with an actual
classification of the configured URL: loopback, RFC1918/ULA private ranges,
``localhost``, and well-known internal DNS suffixes (Kubernetes'
``.svc.cluster.local``, ``.cluster.local``, ``.internal``, ``.local``) count
as "stays within our own infrastructure"; everything else — including an
empty/unparseable URL — is treated as external (fail-closed: redact when in
doubt, matching Blueprint Principle 2).
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

_INTERNAL_HOSTNAMES = {"localhost"}
_INTERNAL_HOST_SUFFIXES = (".local", ".internal", ".svc.cluster.local", ".cluster.local")


def is_internal_endpoint(url: str) -> bool:
    """True if `url`'s host is within this deployment's own infrastructure."""
    if not url:
        return False
    host = urlparse(url).hostname
    if not host:
        return False
    host = host.lower()
    if host in _INTERNAL_HOSTNAMES or host.endswith(_INTERNAL_HOST_SUFFIXES):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # a real external hostname (api.openai.com, etc.)
    return ip.is_loopback or ip.is_private
