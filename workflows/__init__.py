"""Workflow patterns for AI_ENGINE (MASTER_INSTRUCTION.md Bab 24).

Tahap 2 shipped Sequential and Parallel. Tahap 4 adds Reflection, Voting, and
Consensus (selectable via ``WORKFLOWS``) plus the Human Approval gate
(``approval.py`` — not itself a selectable mode, see its module docstring).
Recursive and Self-Critique remain for a later phase.
"""
from .approval import ApprovalRequest, HumanApprovalGate
from .base import BaseWorkflow, WorkflowResult
from .consensus import ConsensusWorkflow
from .parallel import ParallelWorkflow
from .reflection import ReflectionWorkflow
from .sequential import SequentialWorkflow
from .voting import VotingWorkflow

# Registry of the workflow patterns available today (Bab 24 selection).
WORKFLOWS: dict[str, type[BaseWorkflow]] = {
    "sequential": SequentialWorkflow,
    "parallel": ParallelWorkflow,
    "reflection": ReflectionWorkflow,
    "voting": VotingWorkflow,
    "consensus": ConsensusWorkflow,
}

__all__ = [
    "ApprovalRequest",
    "BaseWorkflow",
    "ConsensusWorkflow",
    "HumanApprovalGate",
    "ParallelWorkflow",
    "ReflectionWorkflow",
    "SequentialWorkflow",
    "VotingWorkflow",
    "WORKFLOWS",
    "WorkflowResult",
]
