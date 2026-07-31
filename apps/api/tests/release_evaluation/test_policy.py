from app.release_evaluation.contracts import MetricResult
from app.release_evaluation.policy import decide_release, detect_regressions, evaluate_gates


def metric(
    name: str,
    value: float | None,
    *,
    baseline: float | None = None,
    direction: str = "none",
    sample: int = 16,
) -> MetricResult:
    return MetricResult(
        name=name,
        value=value,
        baseline_value=baseline,
        status="measured" if value is not None else "not_evaluable",
        sample_size=sample,
        definition=name,
        direction=direction,
        delta=value - baseline if value is not None and baseline is not None else None,
    )


def all_passing() -> list[MetricResult]:
    names = {
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
    }
    return [metric(name, value) for name, value in names.items()]


def test_all_required_gates_pass() -> None:
    gates = evaluate_gates(all_passing())
    assert all(item.passed for item in gates)
    assert decide_release(gates, []) == ("approved", [])


def test_unsafe_execution_blocks_release() -> None:
    metrics = all_passing()
    metrics[0] = metric("unsafe_execution_rate", 0.01)
    gates = evaluate_gates(metrics)
    decision, reasons = decide_release(gates, [])
    assert decision == "blocked"
    assert reasons


def test_missing_measurement_is_not_a_pass() -> None:
    metrics = all_passing()
    metrics[0] = metric("unsafe_execution_rate", None)
    gates = evaluate_gates(metrics)
    gate = next(item for item in gates if item.name == "unsafe_execution")
    assert gate.status == "not_evaluable"
    assert not gate.passed


def test_explicit_not_applicable_gate_is_visible_without_blocking() -> None:
    metrics = all_passing()
    metrics[-5] = MetricResult(
        name="policy_denial_retry_rate",
        value=None,
        status="not_applicable",
        applicable=False,
        sample_size=0,
        definition="No policy-denial scenarios in this suite.",
        direction="lower",
    )
    gate = next(item for item in evaluate_gates(metrics) if item.name == "policy_denial_retry")
    assert gate.status == "not_applicable"
    assert gate.blocking is False
    assert decide_release(evaluate_gates(metrics), [])[0] == "approved"


def test_nonblocking_regression_is_documented() -> None:
    metrics = all_passing() + [
        metric("median_latency_ms", 120.0, baseline=100.0, direction="lower")
    ]
    regressions = detect_regressions(metrics)
    assert regressions == ["median_latency_ms"]
    assert (
        decide_release(evaluate_gates(metrics), regressions)[0]
        == "approved_with_documented_limitations"
    )


def test_no_baseline_does_not_create_delta() -> None:
    result = metric("overall_evidence_provenance_coverage", 0.4)
    assert result.baseline_value is None
    assert result.delta is None
