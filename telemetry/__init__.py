"""Telemetry — Observability + Cost (MASTER_INSTRUCTION.md Bab 27, 33-35, 56, Tahap 6).

Every module here is a passive Event Bus subscriber (Bab 23 prinsip 1) except
``monitoring.py``, which aggregates their output into the Bab 62 dashboards
and ``check_alerts()`` (Bab 35 rule 2). Zero coupling to Dispatcher/
Orchestrator internals — they only read events those already publish.
"""
from .cost_tracker import CostTracker, estimate_cost, price_for
from .logging import get_logger
from .metrics import MetricsCollector, percentile
from .monitoring import (
    Alert,
    agent_dashboard,
    check_alerts,
    check_readiness,
    cost_dashboard,
    health_dashboard,
    latency_dashboard,
    memory_dashboard,
    provider_dashboard,
    queue_dashboard,
    workflow_dashboard,
)
from .tracing import Span, Tracer

__all__ = [
    "Alert",
    "CostTracker",
    "MetricsCollector",
    "Span",
    "Tracer",
    "agent_dashboard",
    "check_alerts",
    "check_readiness",
    "cost_dashboard",
    "estimate_cost",
    "get_logger",
    "health_dashboard",
    "latency_dashboard",
    "memory_dashboard",
    "percentile",
    "price_for",
    "provider_dashboard",
    "queue_dashboard",
    "workflow_dashboard",
]
