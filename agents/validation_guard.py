"""Validator independence guard (Fase 2, R-08 — DCF v5 mandate: "Builder tidak
boleh menjadi validator dirinya sendiri. Validator harus memiliki
independensi.").

This is the enforcement point — ``agents/capabilities.py`` only assigns a
label, this module is what actually rejects a violation instead of trusting
convention. Wired into ``orchestrator/dispatcher.py``, the one chokepoint
every workflow/caller already routes through: :meth:`Dispatcher.dispatch`
checks ``Task.metadata["validates_agent_ids"]`` (a list of agent_ids whose
output this task is meant to judge) and calls :func:`assert_independent_validator`
before the task runs. Today the only code path that actually sets that
metadata is ``orchestrator/consensus.py::ConsensusEngine.arbitrate`` (grep
confirmed — no other call site dispatches a Task explicitly marked as
validating another agent's output); the check is written generally, keyed
off metadata rather than hardcoded to Consensus, so any future caller
(e.g. an explicit review/critique step) is protected the same way without
touching this module again.

Deliberately NOT wired into ``orchestrator/reflection.py``: that engine's
self-evaluate/revise loop re-dispatches the *same* role to improve its own
output, scored by an algorithmic ``ConfidenceScorer`` (not another agent's
judgment) — a self-correction loop with its own safety net (escalates to
Human Approval on low confidence), not a validation claim this guard's
"builder ≠ validator" rule is about. Forcing independent review into
Reflection is a larger, separate design change, not bundled into this pass.
"""
from __future__ import annotations

from typing import Iterable

from .base_agent import BaseAgent
from .capabilities import AgentCapability


class ValidatorNotIndependentError(Exception):
    """Raised when the agent about to run cannot legitimately validate the
    output it's being asked to judge — either it isn't a VALIDATOR-capability
    role, or it's the same agent that produced the output in question.

    Deliberately not caught by ``Dispatcher.dispatch``'s retry/fallback loop
    (that loop is for transient ``ProviderError``s) — this is a programming/
    policy violation, not a runtime provider failure, so it propagates
    uncaught, the same way ``task_manager.IllegalTransitionError`` does for
    illegal state transitions rather than silently corrupting state.
    """


def assert_independent_validator(producer_agent_ids: Iterable[str], validator: BaseAgent) -> None:
    """Raise unless ``validator`` is a VALIDATOR-capability agent distinct
    from every id in ``producer_agent_ids``.

    Args:
        producer_agent_ids: ``agent_id``s of whichever agent(s) produced the
            output ``validator`` is about to judge.
        validator: The agent resolved to run the validating task.
    """
    if validator.capability is not AgentCapability.VALIDATOR:
        raise ValidatorNotIndependentError(
            f"agent {validator.agent_id!r} (role={validator.role!r}, "
            f"capability={validator.capability.value!r}) cannot act as a validator — "
            "only VALIDATOR-capability roles may judge another agent's output"
        )
    producer_ids = set(producer_agent_ids)
    if validator.agent_id in producer_ids:
        raise ValidatorNotIndependentError(
            f"agent {validator.agent_id!r} cannot validate its own output "
            f"(producer_agent_ids={sorted(producer_ids)})"
        )
