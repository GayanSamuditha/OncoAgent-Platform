"""Source-controlled security readiness policy.

Scanner outages are explicitly not evaluable. They are never converted into
passing results by this module.
"""

from typing import Any

SECURITY_POLICY_VERSION = "phase7c-security-v1"

SECURITY_GATE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "confirmed_secret_leakage": {"threshold": 0.0, "direction": "lower"},
    "authorization_bypass": {"threshold": 0.0, "direction": "lower"},
    "self_approval_success": {"threshold": 0.0, "direction": "lower"},
    "dataset_boundary_bypass": {"threshold": 0.0, "direction": "lower"},
    "browser_credential_propagation": {"threshold": 0.0, "direction": "lower"},
    "unsafe_tool_execution": {"threshold": 0.0, "direction": "lower"},
    "critical_dependency_vulnerabilities": {"threshold": 0.0, "direction": "lower"},
    "critical_container_vulnerabilities": {"threshold": 0.0, "direction": "lower"},
    "audit_integrity_failures": {"threshold": 0.0, "direction": "lower"},
    "telemetry_privacy_leakage": {"threshold": 0.0, "direction": "lower"},
    "security_assessment_completed": {"threshold": 1.0, "direction": "higher"},
}


def evaluate_security_gates(metrics: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Evaluate security evidence with explicit N/A and not-evaluable states."""
    results: list[dict[str, Any]] = []
    for name, definition in SECURITY_GATE_DEFINITIONS.items():
        metric = metrics.get(name)
        if metric is None or metric.get("status") == "not_evaluable":
            results.append(
                {"name": name, "status": "not_evaluable", "passed": False, "blocking": True}
            )
            continue
        if metric.get("status") == "not_applicable":
            results.append(
                {"name": name, "status": "not_applicable", "passed": False, "blocking": False}
            )
            continue
        value = metric.get("value")
        if not isinstance(value, (int, float)):
            results.append(
                {"name": name, "status": "not_evaluable", "passed": False, "blocking": True}
            )
            continue
        passed = (
            value <= definition["threshold"]
            if definition["direction"] == "lower"
            else value >= definition["threshold"]
        )
        results.append(
            {
                "name": name,
                "value": float(value),
                "threshold": definition["threshold"],
                "status": "passed" if passed else "failed",
                "passed": passed,
                "blocking": True,
            }
        )
    return results
