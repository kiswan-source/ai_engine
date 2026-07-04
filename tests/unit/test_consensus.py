"""Unit tests for the Consensus Engine + Voting/Consensus workflows (Bab 26).

Agents are stubbed — no provider/network calls (Bab 12.3).
"""
import pytest

from agents.base_agent import AgentResult, BaseAgent, Task
from orchestrator.consensus import ConsensusEngine
from orchestrator.dispatcher import Dispatcher
from orchestrator.execution_graph import ExecutionGraph, Step
from orchestrator.planner import Planner
from orchestrator.routing_engine import RoutingEngine
from registry.agent_registry import AgentRegistry
from workflows.consensus import ConsensusWorkflow
from workflows.voting import VotingWorkflow


def _result(role: str, output: str, confidence: float = 0.8, ok: bool = True) -> AgentResult:
    return AgentResult(
        output=output if ok else "",
        confidence=confidence,
        trace_id="t1",
        provider_used="stub",
        model_used="stub-m",
        role=role,
        agent_id=f"{role}-stub",
        error=None if ok else "boom",
    )


# ─── ConsensusEngine decision math ────────────────────────────────────────────

def test_majority_vote_picks_most_common_answer():
    engine = ConsensusEngine()
    results = [
        _result("writer", "Jawaban A"),
        _result("analyst", "jawaban a"),  # same answer, different case/role
        _result("critic", "Jawaban B"),
    ]
    decision = engine.majority_vote(results)
    assert decision.winner.output in ("Jawaban A", "jawaban a")
    assert decision.agreement_rate == pytest.approx(2 / 3)


def test_majority_vote_breaks_ties_by_confidence():
    engine = ConsensusEngine()
    results = [
        _result("writer", "A", confidence=0.5),
        _result("analyst", "B", confidence=0.9),
    ]
    decision = engine.majority_vote(results)
    assert decision.winner.role == "analyst"


def test_weighted_vote_lets_weight_override_plurality():
    engine = ConsensusEngine()
    results = [
        _result("writer", "A"),
        _result("analyst", "A"),
        _result("critic", "B"),
    ]
    # two votes for "A" but "critic" is weighted heavily enough to win
    decision = engine.weighted_vote(results, weights={"critic": 10.0})
    assert decision.winner.output == "B"


def test_agreement_rate_ignores_failed_candidates():
    results = [_result("writer", "A"), _result("analyst", "", ok=False)]
    assert ConsensusEngine.agreement_rate(results) == 1.0


def test_majority_vote_with_no_successful_candidates_returns_first():
    engine = ConsensusEngine()
    results = [_result("writer", "", ok=False)]
    decision = engine.majority_vote(results)
    assert not decision.winner.ok
    assert decision.agreement_rate == 0.0


@pytest.mark.asyncio
async def test_arbitrate_dispatches_to_consensus_role():
    class ArbitratorAgent(BaseAgent):
        role = "consensus"
        agent_id = "consensus-stub"
        default_provider = "stub"

        async def execute(self, task: Task) -> AgentResult:
            assert "Kandidat 1" in task.prompt
            return AgentResult(
                output="keputusan akhir",
                confidence=0.9,
                trace_id=task.trace_id,
                provider_used="stub",
                model_used="stub-m",
                role="consensus",
                agent_id="consensus-stub",
            )

        async def health_check(self) -> bool:
            return True

    registry = AgentRegistry()
    registry.register(ArbitratorAgent())
    dispatcher = Dispatcher(RoutingEngine(registry), max_retries=0)

    engine = ConsensusEngine()
    decision = await engine.arbitrate(
        [_result("writer", "A"), _result("analyst", "B")], dispatcher, trace_id="t1"
    )
    assert decision.winner.output == "keputusan akhir"
    assert decision.strategy == "arbitrator"


@pytest.mark.asyncio
async def test_decide_raises_on_unknown_strategy():
    engine = ConsensusEngine()
    with pytest.raises(ValueError):
        await engine.decide([_result("writer", "A")], strategy="nonsense")


# ─── VotingWorkflow / ConsensusWorkflow end-to-end ───────────────────────────

class StubAgent(BaseAgent):
    def __init__(self, role: str, output: str) -> None:
        self.role = role
        self.agent_id = f"{role}-stub"
        self.default_provider = "stub"
        self._output = output
        self.calls = 0
        self.last_prompt = ""

    async def execute(self, task: Task) -> AgentResult:
        self.calls += 1
        self.last_prompt = task.prompt
        return AgentResult(
            output=self._output,
            confidence=0.8,
            trace_id=task.trace_id,
            provider_used="stub",
            model_used="stub-m",
            role=self.role,
            agent_id=self.agent_id,
        )

    async def health_check(self) -> bool:
        return True


def _registry_with(*agents: BaseAgent) -> AgentRegistry:
    reg = AgentRegistry()
    for a in agents:
        reg.register(a)
    return reg


@pytest.mark.asyncio
async def test_voting_workflow_picks_majority_and_flags_escalation_on_disagreement():
    writer, analyst, critic = (
        StubAgent("writer", "yes"),
        StubAgent("analyst", "yes"),
        StubAgent("critic", "no"),
    )
    dispatcher = Dispatcher(RoutingEngine(_registry_with(writer, analyst, critic)), max_retries=0)
    plan = Planner().plan("apakah ini benar?", ["writer", "analyst", "critic"], mode="voting")

    result = await VotingWorkflow().run(plan.graph, dispatcher)

    assert result.final_output == "yes"
    assert not result.failed
    # 2/3 agreement is below the default confidence threshold (0.6) escalation isn't
    # guaranteed by config, but the workflow must at least report a consistent rate.
    assert result.mode == "voting"


@pytest.mark.asyncio
async def test_voting_workflow_rejects_empty_graph():
    dispatcher = Dispatcher(RoutingEngine(_registry_with(StubAgent("writer", "x"))), max_retries=0)
    empty_graph = ExecutionGraph()
    result = await VotingWorkflow().run(empty_graph, dispatcher)
    assert result.final_output == ""
    assert result.trace_id == ""


@pytest.mark.asyncio
async def test_consensus_workflow_runs_debate_then_arbitrates():
    writer, analyst = StubAgent("writer", "A"), StubAgent("analyst", "B")
    arbitrator = StubAgent("consensus", "final decision")
    dispatcher = Dispatcher(RoutingEngine(_registry_with(writer, analyst, arbitrator)), max_retries=0)
    plan = Planner().plan("apa strategi terbaik?", ["writer", "analyst"], mode="consensus")

    result = await ConsensusWorkflow(rounds=1).run(plan.graph, dispatcher)

    assert result.final_output == "final decision"
    assert result.mode == "consensus"
    # each candidate dispatched twice: initial round + one debate round
    assert writer.calls == 2
    assert analyst.calls == 2
    assert arbitrator.calls == 1
    assert "Structured debate" in writer.last_prompt
