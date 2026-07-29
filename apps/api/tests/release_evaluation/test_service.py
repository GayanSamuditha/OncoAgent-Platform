from app.release_evaluation.contracts import ReleaseCandidate
from app.release_evaluation.service import evaluate_candidate


def candidate() -> ReleaseCandidate:
    return ReleaseCandidate(
        candidate_id="test-candidate",
        candidate_version="test-v1",
        baseline_id="test-baseline",
        baseline_version="baseline-v1",
        dataset_id="dataset-a",
        evaluation_suite_version="suite-v1",
    )


def passing_metrics() -> dict[str, float | int]:
    return {
        "unsafe_execution_rate": 0.0,
        "policy_violation_prevention_rate": 1.0,
        "human_review_compliance_rate": 1.0,
        "included_patient_required_criterion_provenance_coverage": 1.0,
        "applicable_lifecycle_audit_completeness": 1.0,
        "orphan_mcp_request_rate": 0.0,
        "duplicate_business_record_rate": 0.0,
        "policy_denial_retry_rate": 0.0,
        "cancellation_finalization_rate": 0.0,
        "authorization_bypass_rate": 0.0,
        "self_approval_success_rate": 0.0,
        "telemetry_redaction_violation_rate": 0.0,
        "overall_evidence_provenance_coverage": 0.8,
        "sample_size": 16,
    }


def test_passing_candidate_is_approved_without_overall_evidence_gate() -> None:
    report = evaluate_candidate(
        candidate(), passing_metrics(), None, baseline_reference={"available": False}
    )
    assert report.decision == "approved"
    evidence = next(
        item for item in report.metrics if item.name == "overall_evidence_provenance_coverage"
    )
    assert evidence.value == 0.8


def test_missing_baseline_is_explicit_and_does_not_create_a_delta() -> None:
    report = evaluate_candidate(
        candidate(), passing_metrics(), None, baseline_reference={"available": False}
    )
    latency = next(item for item in report.metrics if item.name == "median_latency_ms")
    assert latency.value is None
    assert latency.baseline_value is None
    assert latency.delta is None


def test_security_evidence_is_a_blocking_release_extension() -> None:
    evidence = {
        name: {"status": "measured", "value": 0.0}
        for name in (
            "confirmed_secret_leakage",
            "authorization_bypass",
            "self_approval_success",
            "dataset_boundary_bypass",
            "browser_credential_propagation",
            "unsafe_tool_execution",
            "critical_dependency_vulnerabilities",
            "critical_container_vulnerabilities",
            "audit_integrity_failures",
            "telemetry_privacy_leakage",
        )
    }
    evidence["security_assessment_completed"] = {"status": "measured", "value": 1.0}
    report = evaluate_candidate(
        candidate(),
        {**passing_metrics(), "security_metrics": evidence},
        None,
        baseline_reference={"available": False},
    )
    assert all(gate.passed for gate in report.gates if gate.name in evidence)


def test_security_evidence_unavailable_blocks_without_inference() -> None:
    report = evaluate_candidate(
        candidate(),
        {
            **passing_metrics(),
            "security_metrics": {
                "critical_dependency_vulnerabilities": {"status": "not_evaluable"}
            },
        },
        None,
        baseline_reference={"available": False},
    )
    gate = next(gate for gate in report.gates if gate.name == "critical_dependency_vulnerabilities")
    assert gate.status == "not_evaluable"
    assert report.decision == "blocked"
