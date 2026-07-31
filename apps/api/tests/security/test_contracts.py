from datetime import date

from app.security.contracts import RetentionRule, SecurityFinding


def test_security_contracts_are_version_boundary_models() -> None:
    finding = SecurityFinding(
        finding_id="finding-1",
        category="secret_scan",
        severity="high",
        state="accepted_risk",
        title="Development scanner unavailable",
        reason="Recorded without scanner output.",
        owner="platform_operator",
        expires_on=date(2026, 12, 31),
        compensating_control="local-only",
    )
    assert finding.severity == "high"
    rule = RetentionRule(
        rule_id="audit",
        category="audit_records",
        duration_days=None,
        rationale="Institutional history",
        deletion_method="none",
        exception_behavior="hold",
        owner="governance_officer",
        review_date=date(2026, 12, 31),
    )
    assert rule.duration_days is None
