"""Structured Logging (MASTER_INSTRUCTION.md Bab 34) — re-exports the Bab 11 logger.

Bab 34's table lists ``telemetry/logging.py`` as a module, but Bab 11's
structured-logging standard is already fully implemented by
``core.utils.logger`` (structlog, JSON-capable, used everywhere in the
codebase). Duplicating that configuration here would just create a second
place to keep in sync — this module is a single canonical import path
(``from telemetry.logging import get_logger``) for callers that think of
logging as part of the telemetry surface, without a second structlog config.
"""
from __future__ import annotations

from core.utils.logger import get_logger

__all__ = ["get_logger"]
