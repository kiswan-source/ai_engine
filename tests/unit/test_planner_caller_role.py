"""Fase 14 (DCF v5 mandate — orchestrator agent tool access): Planner must
stamp ``caller_role`` onto every step's ``Task.metadata`` when given one, and
must NOT invent the key when it wasn't given — the RBAC gate downstream
(``agents/generic_agent.py``) treats a missing key the same as
``ToolRegistry.execute``'s existing "no role, no check" default.
"""
from orchestrator.planner import Planner


def test_plan_stamps_caller_role_into_every_task_metadata():
    plan = Planner().plan(prompt="tulis laporan", roles=["research", "writer"], caller_role="admin")
    steps = plan.graph.linear_order()
    assert len(steps) == 2
    for step in steps:
        assert step.task.metadata["caller_role"] == "admin"


def test_plan_omits_caller_role_key_when_not_given():
    plan = Planner().plan(prompt="tulis laporan", roles=["writer"])
    step = plan.graph.linear_order()[0]
    assert "caller_role" not in step.task.metadata
    # step_index must still be there — caller_role wasn't added by overwriting metadata.
    assert step.task.metadata["step_index"] == 0
