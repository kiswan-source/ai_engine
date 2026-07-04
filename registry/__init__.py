"""Registry layer for AI_ENGINE (MASTER_INSTRUCTION.md Bab 19-21).

Central catalogues for providers and models. Agent Registry (Bab 19),
Tool Registry (Bab 21), and Workflow Registry are added in later phases.
"""
from . import model_registry, provider_registry
from .model_registry import ModelAssignment, resolve
from .provider_registry import (
    ProviderConfig,
    get_provider_config,
    list_enabled_providers,
    list_providers,
)

__all__ = [
    "ModelAssignment",
    "ProviderConfig",
    "get_provider_config",
    "list_enabled_providers",
    "list_providers",
    "model_registry",
    "provider_registry",
    "resolve",
]
