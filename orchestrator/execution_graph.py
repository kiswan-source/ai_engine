"""Execution Graph — represents a task plan as a DAG (MASTER_INSTRUCTION.md Bab 18).

A workflow is a set of :class:`Step` nodes with dependencies. The graph exposes
a topological layering: each layer is a group of steps whose dependencies are
all satisfied, so the workflow engine can run a layer's steps in parallel and
layers in sequence — covering both sequential and parallel patterns (Bab 24).
Cycles and dangling dependencies are rejected up front (a DAG must stay acyclic).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from agents.base_agent import Task


class GraphValidationError(Exception):
    """Raised when the graph has a missing dependency or a cycle."""


@dataclass
class Step:
    """A single node in the execution graph."""

    step_id: str
    task: Task
    depends_on: tuple[str, ...] = ()


@dataclass
class ExecutionGraph:
    """Directed acyclic graph of execution steps."""

    steps: dict[str, Step] = field(default_factory=dict)

    def add_step(self, step: Step) -> None:
        if step.step_id in self.steps:
            raise GraphValidationError(f"duplicate step id: {step.step_id!r}")
        self.steps[step.step_id] = step

    def validate(self) -> None:
        """Check every dependency exists and the graph is acyclic."""
        for step in self.steps.values():
            for dep in step.depends_on:
                if dep not in self.steps:
                    raise GraphValidationError(
                        f"step {step.step_id!r} depends on unknown step {dep!r}"
                    )
        # Kahn's algorithm doubles as cycle detection below.
        self.topological_layers()

    def topological_layers(self) -> list[list[Step]]:
        """Return steps grouped into dependency layers (Kahn's algorithm).

        Layer *i* contains steps whose dependencies all resolved in layers
        ``< i``; steps within a layer are mutually independent and may run
        concurrently.

        Raises:
            GraphValidationError: If a cycle prevents full ordering.
        """
        indegree = {sid: len(step.depends_on) for sid, step in self.steps.items()}
        dependents: dict[str, list[str]] = {sid: [] for sid in self.steps}
        for step in self.steps.values():
            for dep in step.depends_on:
                dependents[dep].append(step.step_id)

        ready = [sid for sid, deg in indegree.items() if deg == 0]
        layers: list[list[Step]] = []
        seen = 0
        while ready:
            layer_ids = sorted(ready)  # deterministic ordering
            ready = []
            layers.append([self.steps[sid] for sid in layer_ids])
            seen += len(layer_ids)
            for sid in layer_ids:
                for child in dependents[sid]:
                    indegree[child] -= 1
                    if indegree[child] == 0:
                        ready.append(child)

        if seen != len(self.steps):
            raise GraphValidationError("cycle detected in execution graph")
        return layers

    def linear_order(self) -> list[Step]:
        """Flatten the graph into a single valid sequential order."""
        return [step for layer in self.topological_layers() for step in layer]
