"""Workflow patterns for AI_ENGINE (MASTER_INSTRUCTION.md Bab 24).

Tahap 2 ships Sequential and Parallel. Recursive, Reflection, Voting, Consensus,
Self-Critique, and Human Approval arrive in later phases (Tahap 4).
"""
from .base import BaseWorkflow, WorkflowResult
from .parallel import ParallelWorkflow
from .sequential import SequentialWorkflow

# Registry of the workflow patterns available today (Bab 24 selection).
WORKFLOWS: dict[str, type[BaseWorkflow]] = {
    "sequential": SequentialWorkflow,
    "parallel": ParallelWorkflow,
}

__all__ = ["BaseWorkflow", "ParallelWorkflow", "SequentialWorkflow", "WORKFLOWS", "WorkflowResult"]
