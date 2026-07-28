"""Versioned, source-controlled resilience scenario registry."""

from typing import Literal, cast

from app.resilience.contracts import CertificationScenario

SCENARIO_REGISTRY_VERSION = "phase5c-scenarios-v1"


def resilience_scenarios() -> list[CertificationScenario]:
    prerequisites = ["local Temporal, API, PostgreSQL, and observability stack"]
    rows = [
        ("worker-activity-interruption", "Worker termination during an executing Activity", "worker_interrupted", "retryable", "Activity boundary", "awaiting_human_review"),
        ("ollama-temporary-unavailable", "One-shot temporary Ollama failure", "ollama_unavailable", "retryable", "Activity boundary", "awaiting_human_review"),
        ("mcp-temporary-transport-failure", "One-shot temporary MCP transport failure", "mcp_transport_failure", "retryable", "Activity boundary", "awaiting_human_review"),
        ("fastapi-restart", "FastAPI restart while Temporal execution remains active", None, "none", "Temporal workflow history", "accepted"),
        ("worker-review-wait-restart", "Worker restart during human-review wait", None, "none", "durable review wait", "accepted"),
        ("activity-cancellation", "Cancellation while a heartbeat-producing Activity executes", None, "non_retryable", "cancellation checkpoint", "cancelled"),
        ("review-wait-cancellation", "Cancellation while waiting for review", None, "non_retryable", "review wait", "cancelled"),
        ("duplicate-run-submission", "Duplicate idempotent run submission", None, "none", "idempotency reservation", "created"),
        ("duplicate-review-submission", "Duplicate review decision", None, "non_retryable", "terminal review record", "conflict"),
        ("conflicting-review-decision", "Conflicting review decision", None, "non_retryable", "terminal review record", "conflict"),
        ("safety-policy-rejection", "Unsafe request rejected before tools", "safety_policy_rejection", "non_retryable", "policy precheck", "rejected"),
        ("dataset-policy-denial", "Dataset outside allowlist denied", "dataset_policy_denied", "non_retryable", "dataset policy", "rejected"),
        ("authorization-denial", "Unauthorized reviewer or actor denied", "authorization_denied", "non_retryable", "authorization boundary", "rejected"),
        ("unknown-model-profile", "Unknown model profile rejected by schema", "invalid_request_schema", "non_retryable", "request validation", "rejected"),
        ("temporal-unavailable", "Temporal unavailable returns explicit failure", "temporal_unavailable", "none", "API admission", "failed"),
        ("temporal-server-restart", "Temporal server restart with persisted workflow history", None, "retryable", "Temporal history", "awaiting_human_review"),
    ]
    return [
        CertificationScenario(
            scenario_id=sid,
            description=desc,
            injected_failure=failure,
            expected_retry_classification=cast(
                Literal["retryable", "non_retryable", "none"], classification
            ),
            expected_activity_attempts=2 if classification == "retryable" else None,
            expected_recovery_boundary=boundary,
            expected_terminal_status=status,
            prerequisites=prerequisites,
            expected_business_record_counts={"crew_runs": 1, "crew_tasks": 4, "crew_reviews": 1},
            expected_audit_result="applicable records correlated",
            expected_trace_result="Tempo trace retrievable",
            cleanup_procedure="retain sanitized audit records; stop test worker configuration",
        )
        for sid, desc, failure, classification, boundary, status in rows
    ]
