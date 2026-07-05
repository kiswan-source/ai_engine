"""PluginInterface (MASTER_INSTRUCTION.md Bab 59.1) — the one contract that
matters to the rest of the system. Orchestrator/Workflow/agent tool registry
only ever see this interface, never a concrete plugin class (Dependency
Inversion, Bab 4.3) — adding a new plugin never requires touching those
callers, only `registry/plugin_registry.py`'s catalog.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class PluginInterface(ABC):
    """A plugin exposes exactly one capability and describes itself via `manifest()`."""

    name: str
    version: str
    description: str
    permission_action: str

    @abstractmethod
    def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Run the plugin's capability and return a JSON-serializable result."""

    def manifest(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "permission_action": self.permission_action,
        }
