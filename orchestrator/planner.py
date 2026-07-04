"""Planner — turns a request into an execution plan (MASTER_INSTRUCTION.md Bab 18).

Deterministic/rule-based by design (Bab 18): given a prompt and an ordered list
of agent roles, it builds an :class:`ExecutionGraph`. Chained modes
(``sequential``, ``reflection``) make each step depend on the previous one;
independent modes (``parallel``, ``voting``, ``consensus``) leave every step
free of dependencies so its workflow can dispatch them all at once. An
LLM-driven planner (Planner Agent, Bab 17) can replace this later without
changing the orchestrator contract.
"""
from __future__ import annotations

from dataclasses import dataclass

from agents.base_agent import Task, new_id

from .execution_graph import ExecutionGraph, Step

# Modes whose steps chain (each depends on the previous); all other known
# modes run their steps independently (Bab 24).
_CHAINED_MODES = frozenset({"sequential", "reflection"})
_KNOWN_MODES = _CHAINED_MODES | frozenset({"parallel", "voting", "consensus"})


@dataclass
class Plan:
    """The chosen workflow mode plus the graph of steps to run."""

    mode: str  # one of workflows.WORKFLOWS
    graph: ExecutionGraph
    trace_id: str


class Planner:
    """Builds execution plans from a prompt and a list of roles."""

    def plan(
        self,
        prompt: str,
        roles: list[str],
        mode: str = "sequential",
        trace_id: str | None = None,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Plan:
        """Create a :class:`Plan` for ``roles`` over ``prompt``.

        Args:
            roles: Ordered agent roles participating in the workflow. For
                ``voting``/``consensus`` these are the independent candidates
                (e.g. ``["writer", "analyst", "critic"]``) all answering the
                same prompt.
            mode: A key of ``workflows.WORKFLOWS`` (sequential/parallel/
                reflection/voting/consensus).

        Raises:
            ValueError: If ``roles`` is empty or ``mode`` is unknown.
        """
        if not roles:
            raise ValueError("plan requires at least one role")
        if mode not in _KNOWN_MODES:
            raise ValueError(f"unknown workflow mode: {mode!r} (have: {sorted(_KNOWN_MODES)})")

        trace_id = trace_id or new_id()
        graph = ExecutionGraph()
        prev_id: str | None = None
        for index, role in enumerate(roles):
            step_id = f"s{index}-{role}"
            task = Task(
                role=role,
                prompt=prompt,
                trace_id=trace_id,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                metadata={"step_index": index},
            )
            depends = (prev_id,) if (mode in _CHAINED_MODES and prev_id) else ()
            graph.add_step(Step(step_id=step_id, task=task, depends_on=depends))
            prev_id = step_id

        graph.validate()
        return Plan(mode=mode, graph=graph, trace_id=trace_id)
