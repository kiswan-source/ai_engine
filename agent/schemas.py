from typing import Any, List, Optional
from pydantic import BaseModel, Field

class ToolCall(BaseModel):
    tool: str
    input: Optional[Any] = None

class StepResult(BaseModel):
    step: int
    tool: str
    input: Any
    output: Any
    success: bool
    error: Optional[str] = None

class AgentResult(BaseModel):
    goal: str
    success: bool
    steps_taken: int
    steps: List[StepResult]
    final_output: Any
    output_files: List[str] = Field(default_factory=list)
    error: Optional[str] = None
