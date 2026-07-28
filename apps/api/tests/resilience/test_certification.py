from app.resilience.contracts import CertificationObservation
from app.resilience.registry import resilience_scenarios
from app.resilience.validators import duplicate_counts, resilience_scorecard


def test_registry_has_versioned_required_scenarios() -> None:
    scenarios = resilience_scenarios()
    ids = {item.scenario_id for item in scenarios}
    assert len(scenarios) == 16
    assert {
        "activity-cancellation",
        "mcp-temporary-transport-failure",
        "temporal-unavailable",
    } <= ids


def test_duplicate_counts_are_explicit() -> None:
    assert duplicate_counts(tasks=4, outputs=1, reviews=1, completions=1, lineage=1) == {
        "crew_tasks": 0,
        "crew_outputs": 0,
        "crew_reviews": 0,
        "completion_events": 0,
        "mcp_lineage": 0,
    }


def test_scorecard_does_not_hide_empty_retry_denominator() -> None:
    item = CertificationObservation(
        certification_id="cert-1", scenario_id="safe", final_status="rejected",
        audit_result="complete", trace_result="not_applicable",
        redaction_result="clean", passed=True,
    )
    scorecard = resilience_scorecard([item])
    assert scorecard["retryable_recovery_success"]["sample_size"] == 0
    assert scorecard["retryable_recovery_success"]["passed"] is False
