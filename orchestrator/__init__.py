"""Orchestrator layer for AI_ENGINE (MASTER_INSTRUCTION.md Bab 18).

The coordination brain of the multi-agent system. Tahap 2 provided planning,
routing, dispatch with fallback, sequential/parallel workflows, and the task
state machine. Tahap 4 adds real Confidence Scoring (Bab 28), the Reflection
Engine (Bab 25), and the Consensus Engine (Bab 26); the Orchestrator wires
their escalation path into Human Approval (``workflows.approval``, Bab 61).
"""
from .confidence import ConfidenceBreakdown, ConfidenceScorer, threshold_for
from .consensus import ConsensusDecision, ConsensusEngine
from .dispatcher import Dispatcher
from .execution_graph import ExecutionGraph, GraphValidationError, Step
from .orchestrator import Orchestrator
from .planner import Plan, Planner
from .reflection import ReflectionEngine, ReflectionOutcome
from .routing_engine import RoutingEngine, RoutingError
from .task_manager import IllegalTransitionError, State, TaskManager, TaskRecord

__all__ = [
    "ConfidenceBreakdown",
    "ConfidenceScorer",
    "ConsensusDecision",
    "ConsensusEngine",
    "Dispatcher",
    "ExecutionGraph",
    "GraphValidationError",
    "IllegalTransitionError",
    "Orchestrator",
    "Plan",
    "Planner",
    "ReflectionEngine",
    "ReflectionOutcome",
    "RoutingEngine",
    "RoutingError",
    "State",
    "Step",
    "TaskManager",
    "TaskRecord",
    "threshold_for",
]
