"""Multi-agent layer for AI_ENGINE (MASTER_INSTRUCTION.md Bab 17).

Exposes the agent domain model and the generic role-driven agent. Specialised
per-provider agents (Bab 17.1) are added in later phases.
"""
from .base_agent import AgentResult, BaseAgent, Task, new_id
from .generic_agent import GenericLLMAgent

__all__ = ["AgentResult", "BaseAgent", "GenericLLMAgent", "Task", "new_id"]
