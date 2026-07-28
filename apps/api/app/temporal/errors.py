"""Typed Temporal failure categories and retry classification."""

from temporalio.exceptions import ApplicationError

RETRYABLE_FAILURES = {
    "ollama_unavailable",
    "mcp_transport_failure",
    "postgresql_transient_failure",
    "worker_interrupted",
    "activity_worker_failure",
    "bounded_timeout",
}

NON_RETRYABLE_FAILURES = {
    "safety_policy_rejection",
    "authorization_denied",
    "dataset_policy_denied",
    "invalid_request_schema",
    "invalid_task_contract",
    "final_brief_schema_violation",
    "unsupported_operation",
    "review_authority_missing",
    "deterministic_governance_failure",
    "activity_cancelled",
}


def application_failure(category: str, message: str) -> ApplicationError:
    return ApplicationError(message, type=category, non_retryable=category in NON_RETRYABLE_FAILURES)
