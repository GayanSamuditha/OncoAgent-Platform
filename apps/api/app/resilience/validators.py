"""Deterministic resilience validators and governance scorecard."""

from collections.abc import Iterable

from app.resilience.contracts import CertificationObservation, CertificationScenario


def activity_attempts_from_history(attempts: Iterable[int]) -> list[int]:
    return sorted({int(attempt) for attempt in attempts if int(attempt) >= 1})


def duplicate_counts(*, tasks: int, outputs: int, reviews: int, completions: int, lineage: int) -> dict[str, int]:
    return {
        "crew_tasks": max(tasks - 4, 0),
        "crew_outputs": max(outputs - 1, 0),
        "crew_reviews": max(reviews - 1, 0),
        "completion_events": max(completions - 1, 0),
        "mcp_lineage": max(lineage - 1, 0),
    }


def validate_observation(scenario: CertificationScenario, observation: CertificationObservation) -> list[str]:
    defects: list[str] = []
    acceptable_statuses = {scenario.expected_terminal_status}
    if scenario.expected_terminal_status == "awaiting_human_review":
        acceptable_statuses.add("accepted")
    if scenario.expected_terminal_status not in {"created", "conflict", "rejected", "failed"} and observation.final_status not in acceptable_statuses:
        defects.append("unexpected terminal status")
    if any(value != 0 for value in observation.duplicate_record_counts.values()):
        defects.append("duplicate business records")
    if scenario.expected_retry_classification == "retryable" and max(observation.activity_attempts or [0]) < 2:
        defects.append("retryable scenario did not show Activity attempt 2")
    if scenario.expected_retry_classification == "non_retryable" and max(observation.activity_attempts or [1]) > 1:
        defects.append("non-retryable scenario retried")
    if scenario.scenario_id == "activity-cancellation" and observation.final_status == "cancelled" and observation.trace_result == "available":
        if not observation.heartbeat_observed:
            defects.append("Activity heartbeat was not observed")
        if not observation.cancellation_observed:
            defects.append("Activity-level cancellation heartbeat was not observed")
    if observation.audit_result != "complete":
        defects.append("audit incomplete")
    if observation.trace_result not in {"available", "not_applicable"}:
        defects.append("trace unavailable")
    return defects


def resilience_scorecard(observations: list[CertificationObservation]) -> dict[str, dict[str, object]]:
    applicable = [item for item in observations if item.final_status != "not_run"]
    def gate(name: str, value: float, threshold: float, sample_size: int) -> dict[str, object]:
        return {"value": value, "threshold": threshold, "sample_size": sample_size, "passed": value >= threshold}
    retryable = [item for item in applicable if item.retry_classification == "retryable"]
    cancellation = [item for item in applicable if item.scenario_id in {"activity-cancellation", "review-wait-cancellation"}]
    return {
        "retryable_recovery_success": gate("retryable_recovery_success", sum(item.passed for item in retryable) / len(retryable) if retryable else 0, 1, len(retryable)),
        "duplicate_business_record_rate": gate("duplicate_business_record_rate", sum(not any(item.duplicate_record_counts.values()) for item in applicable) / len(applicable) if applicable else 0, 1, len(applicable)),
        "cancellation_finalization_prevention": gate("cancellation_finalization_prevention", sum(item.final_status == "cancelled" for item in cancellation) / len(cancellation) if cancellation else 0, 1, len(cancellation)),
        "audit_completeness": gate("audit_completeness", sum(item.audit_result == "complete" for item in applicable) / len(applicable) if applicable else 0, 1, len(applicable)),
        "trace_retrieval": gate("trace_retrieval", sum(item.trace_result in {"available", "not_applicable"} for item in applicable) / len(applicable) if applicable else 0, 1, len(applicable)),
        "telemetry_redaction": gate("telemetry_redaction", sum(item.redaction_result == "clean" for item in applicable) / len(applicable) if applicable else 0, 1, len(applicable)),
    }
