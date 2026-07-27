from typing import Literal

from app.cross_framework.contracts import NormalizedEvaluationResult
from app.cross_framework.metrics import aggregate_results
from app.cross_framework.registry import framework_agents


def _result(framework: Literal["langgraph", "crewai"]) -> NormalizedEvaluationResult:
    return NormalizedEvaluationResult(
        evaluation_run_id="run-1",
        scenario_id="condition",
        framework=framework,
        framework_version="test",
        agent_or_workflow_version="test",
        dataset_id="dataset-1",
        final_status="awaiting_human_review",
        expected_outcome_match=True,
        candidate_count=1,
        included_count=0,
        excluded_count=0,
        unresolved_count=1,
        required_criterion_coverage=1,
        evidence_provenance_coverage=1,
        unsupported_claim_count=0,
        tool_policy_violations=0,
        dataset_policy_violations=0,
        approval_required=True,
        approval_enforced=True,
        safety_rejection=False,
        total_latency_ms=10,
        tool_call_count=2,
        fallback_count=0,
        audit_event_count=3,
        process_recovery_capability="checkpoint_resume",
    )


def test_normalized_metrics_keep_frameworks_separate() -> None:
    output = aggregate_results([_result("langgraph"), _result("crewai")])
    assert set(output) == {"langgraph", "crewai"}
    assert output["langgraph"]["evidence_provenance_coverage"] == 1


def test_registry_has_two_distinct_governance_profiles() -> None:
    agents = {agent.framework: agent for agent in framework_agents()}
    assert agents["LangGraph"].recovery["durable"] is True
    assert agents["CrewAI"].recovery["durable"] is False
    assert agents["CrewAI"].approval_policy["required"] is True
