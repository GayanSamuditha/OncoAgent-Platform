from app.security.policy import evaluate_security_gates


def passing() -> dict[str, dict[str, object]]:
    return {
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
    } | {"security_assessment_completed": {"status": "measured", "value": 1.0}}


def test_security_gates_pass_only_with_measured_evidence() -> None:
    results = evaluate_security_gates(passing())
    assert all(item["passed"] for item in results)


def test_unavailable_scanner_is_not_evaluable_and_blocks() -> None:
    evidence = passing()
    evidence["critical_dependency_vulnerabilities"] = {"status": "not_evaluable"}
    result = next(
        item
        for item in evaluate_security_gates(evidence)
        if item["name"] == "critical_dependency_vulnerabilities"
    )
    assert result == {
        "name": "critical_dependency_vulnerabilities",
        "status": "not_evaluable",
        "passed": False,
        "blocking": True,
    }


def test_not_applicable_is_visible_without_becoming_a_pass() -> None:
    evidence = passing()
    evidence["critical_container_vulnerabilities"] = {"status": "not_applicable"}
    result = next(
        item
        for item in evaluate_security_gates(evidence)
        if item["name"] == "critical_container_vulnerabilities"
    )
    assert result["status"] == "not_applicable"
    assert result["blocking"] is False
