"""Security — Guardrail & Access Control (MASTER_INSTRUCTION.md Bab 30, 31, 58, Tahap 7).

Every external LLM call passes through ``prompt_guard`` (injection) and
``pii_detector`` (redaction) before leaving the system boundary (Bab 30 rule
1) — wired into ``agents/generic_agent.py``, the one choke point every role's
dispatch already goes through. ``output_validator``'s score doubles as
Confidence Scoring's fourth signal (Bab 28, promised since ADR-0007).
``auth``/``permissions`` are complete but not wired into existing routes —
see their module docstrings for why.
"""
from .audit_log import AuditEntry, read_recent, record
from .auth import Principal, get_current_principal, verify_api_key
from .output_validator import ValidationResult, validate
from .permissions import has_permission, require_permission, require_role
from .pii_detector import PIIMatch, detect as detect_pii, redact as redact_pii
from .prompt_guard import GuardResult, check as check_prompt

__all__ = [
    "AuditEntry",
    "GuardResult",
    "PIIMatch",
    "Principal",
    "ValidationResult",
    "check_prompt",
    "detect_pii",
    "get_current_principal",
    "has_permission",
    "read_recent",
    "record",
    "redact_pii",
    "require_permission",
    "require_role",
    "validate",
    "verify_api_key",
]
