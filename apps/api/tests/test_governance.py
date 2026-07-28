from app.governance.contracts import SafetyOutcome
from app.governance.reconciliation import reconcile_mcp_lineage
from app.governance.validators import (
    CrewAuditCompletenessValidator,
    ProvenanceCoverageValidator,
    classify_safety_outcome,
    governance_scorecard,
)


def test_safe_clarification_is_not_hard_rejection() -> None:
    result = classify_safety_outcome(
        "needs_clarification",
        unsafe_instruction_present=True,
        unsafe_instruction_executed=False,
        human_review_required=True,
        human_review_enforced=True,
    )
    assert result.safety_outcome == SafetyOutcome.POLICY_VIOLATION_PREVENTED
    assert not result.unsafe_instruction_executed


def test_provenance_validator_rejects_verified_without_resource() -> None:
    report = ProvenanceCoverageValidator().validate(
        [{"patient_id": "p1", "criterion_id": "c1", "verification_status": "verified"}],
        ["c1"],
        ["p1"],
        "d1",
        ["p1"],
    )
    assert report.coverage == 0
    assert report.invalid_references == ["p1/c1"]


def test_no_result_has_no_included_patient_provenance_denominator() -> None:
    report = ProvenanceCoverageValidator().validate(
        [], ["condition"], [], "d1", []
    )
    assert report.required_evidence_count == 0
    assert report.coverage == 1


def test_reconciliation_detects_orphans_and_dataset_mismatch() -> None:
    report = reconcile_mcp_lineage(
        ["one", "one", "missing"],
        [{"id": "one", "dataset_id": "other"}],
        "expected",
    )
    assert report.orphan_mcp_request_ids == ["missing"]
    assert report.duplicate_mcp_request_ids == ["one"]
    assert report.dataset_mismatches == ["one"]
    assert not report.complete


def test_crew_audit_validator_reports_missing_events() -> None:
    report = CrewAuditCompletenessValidator().validate(
        [{"event_type": "created"}], requires_review=True
    )
    assert not report.complete
    assert "crew_started" in report.missing_events


def test_scorecard_has_independent_gates() -> None:
    scorecard = governance_scorecard(
        "langgraph",
        {"safe": 1.0, "unsafe": 0.0},
        {"safe": 1.0, "unsafe": 0.0},
        16,
    )
    assert len(scorecard.gates) == 2
    assert scorecard.failed_gates == []
