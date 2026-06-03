"""Agent rolling window memory."""
from typing import List, Any
from agent.schemas import StepResult

class Memory:
    def __init__(self, goal: str, max_steps: int = 5):
        self.goal = goal
        self.max_steps = max_steps
        self._steps: List[StepResult] = []
        self._output_files: List[str] = []

    def add(self, result: StepResult):
        self._steps.append(result)
        if len(self._steps) > self.max_steps:
            self._steps = self._steps[-self.max_steps:]
        if result.success and isinstance(result.output, dict) and result.output.get("file"):
            self._output_files.append(result.output["file"])

    def get_steps(self): return list(self._steps)
    def get_output_files(self): return list(self._output_files)
    def step_count(self): return len(self._steps)
    def last_output(self):
        for s in reversed(self._steps):
            if s.success: return s.output
        return None

    def to_context(self) -> str:
        if not self._steps: return "No steps yet."
        lines = [f"Goal: {self.goal}", ""]
        for s in self._steps:
            out = s.output
            if isinstance(out, dict):
                preview = {k: (str(v)[:150]+"…" if k=="text" and len(str(v))>150 else v)
                           for k,v in out.items() if k != "rows"}
                out_str = str(preview)[:300]
            else:
                out_str = str(out)[:300]
            lines.append(f"Step {s.step} [{'OK' if s.success else 'ERR'}] tool={s.tool}\n  in={str(s.input)[:100]}\n  out={out_str}")
            if s.error: lines.append(f"  error={s.error}")
        return "\n".join(lines)
