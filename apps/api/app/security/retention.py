"""Local-development retention policy and dry-run reporting."""

from datetime import date

from app.security.contracts import RetentionRule

RETENTION_RULES = [
    RetentionRule(
        rule_id="synthetic-fhir",
        category="synthetic_fhir",
        duration_days=None,
        rationale="Retained only for bounded local evaluation.",
        deletion_method="explicit dataset cleanup",
        exception_behavior="preserve while an active evaluation references it",
        owner="platform_operator",
        review_date=date(2026, 12, 31),
    ),
    RetentionRule(
        rule_id="workflow-records",
        category="workflow_records",
        duration_days=365,
        rationale="Supports local reproducibility and audit review.",
        deletion_method="guarded operator deletion",
        exception_behavior="preserve during investigation or hold",
        owner="governance_officer",
        review_date=date(2026, 12, 31),
    ),
    RetentionRule(
        rule_id="audit-records",
        category="audit_records",
        duration_days=None,
        rationale="Institutional history must not be automatically deleted.",
        deletion_method="no automatic deletion",
        exception_behavior="hold overrides deletion",
        owner="governance_officer",
        review_date=date(2026, 12, 31),
    ),
    RetentionRule(
        rule_id="telemetry",
        category="traces_and_metrics",
        duration_days=30,
        rationale="Bounded local operational troubleshooting.",
        deletion_method="volume retention policy",
        exception_behavior="preserve exported security evidence",
        owner="platform_operator",
        review_date=date(2026, 12, 31),
    ),
    RetentionRule(
        rule_id="reports",
        category="evaluation_reports",
        duration_days=180,
        rationale="Supports release and resilience comparisons.",
        deletion_method="guarded report cleanup",
        exception_behavior="preserve report referenced by release decision",
        owner="governance_officer",
        review_date=date(2026, 12, 31),
    ),
    RetentionRule(
        rule_id="backups",
        category="development_backups",
        duration_days=30,
        rationale="Bounded local restore testing.",
        deletion_method="explicit backup cleanup",
        exception_behavior="preserve during restore verification",
        owner="platform_operator",
        review_date=date(2026, 12, 31),
    ),
]


def dry_run_retention() -> dict[str, object]:
    return {
        "status": "dry_run",
        "rules": [rule.model_dump(mode="json") for rule in RETENTION_RULES],
        "deletion_performed": False,
        "limitations": [
            "Local synthetic development policy; no legal or regulatory retention claim."
        ],
    }
