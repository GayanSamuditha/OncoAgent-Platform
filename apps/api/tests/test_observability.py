import pytest

from app.core.config import Settings
from app.observability.metrics import (
    API_SERVICE,
    CREW_RUNS,
    CREW_TASK_DURATION,
    CREW_TASKS,
    MCP_ERRORS,
    MCP_REQUESTS,
    ORPHAN_MCP,
    SECURITY_SELF_APPROVAL_DENIALS,
    UNSAFE_PREVENTED,
    VALIDATION_FAILURES,
    WORKER_SERVICE,
    initialize_service_metrics,
    observe_crew_outcome,
    observe_crew_task,
    observe_validation_failure,
    prometheus_payload,
)
from app.observability.telemetry import current_trace_context, observability_status


def test_observability_status_is_safe_when_disabled() -> None:
    settings = Settings(observability_enabled=False)
    status = observability_status(settings)
    assert status["enabled"] is False
    assert status["collector_unavailable_is_non_fatal"] is True
    assert "database_url" not in status


def test_trace_context_never_contains_clinical_values() -> None:
    context = current_trace_context()
    assert set(context) == {"trace_id", "span_id"}
    assert all(value is None or len(value) in {16, 32} for value in context.values())


def test_prometheus_payload_uses_platform_metric_names() -> None:
    payload, media_type = prometheus_payload()
    assert media_type.startswith("text/plain")
    assert b"oncoagent_http_requests_total" in payload


def test_bounded_metrics_are_initialized_with_real_zero_series() -> None:
    initialize_service_metrics(API_SERVICE)
    initialize_service_metrics(WORKER_SERVICE)
    payload, _ = prometheus_payload()
    assert b'outcome="accepted"' in payload
    assert b'task_name="candidate_discovery"' in payload
    assert b'category="self_approval"' in payload
    assert b'validation_type="brief"' in payload
    assert b'oncoagent_orphan_mcp_requests{service="oncoagent-temporal-worker"} 0.0' in payload


def test_accepted_outcome_and_task_duration_are_observed() -> None:
    outcome = CREW_RUNS.labels(
        framework="crewai",
        workflow_type="oncology_research",
        outcome="accepted",
        service=WORKER_SERVICE,
    )
    task = CREW_TASKS.labels(
        task_name="candidate_discovery",
        status="completed",
        service=WORKER_SERVICE,
    )
    duration = CREW_TASK_DURATION.labels(
        task_name="candidate_discovery",
        status="completed",
        service=WORKER_SERVICE,
    )
    outcome_before = outcome._value.get()
    task_before = task._value.get()
    duration_before = sum(bucket.get() for bucket in duration._buckets)
    observe_crew_outcome("accepted")
    observe_crew_task("candidate_discovery", "completed", 0.25)
    assert outcome._value.get() == outcome_before + 1
    assert task._value.get() == task_before + 1
    assert sum(bucket.get() for bucket in duration._buckets) == duration_before + 1


def test_validation_failure_is_bounded_and_observed() -> None:
    metric = VALIDATION_FAILURES.labels(validation_type="brief", service=WORKER_SERVICE)
    before = metric._value.get()
    observe_validation_failure("brief", WORKER_SERVICE)
    assert metric._value.get() == before + 1
    with pytest.raises(ValueError, match="bounded"):
        observe_validation_failure("patient-id", WORKER_SERVICE)


def test_operational_metrics_exclude_high_cardinality_labels() -> None:
    forbidden = {
        "run_id",
        "workflow_id",
        "review_id",
        "patient_id",
        "dataset_id",
        "user_id",
        "trace_id",
        "prompt",
        "url",
    }
    for metric in (
        CREW_RUNS,
        CREW_TASKS,
        CREW_TASK_DURATION,
        MCP_REQUESTS,
        MCP_ERRORS,
        ORPHAN_MCP,
        UNSAFE_PREVENTED,
        VALIDATION_FAILURES,
        SECURITY_SELF_APPROVAL_DENIALS,
    ):
        assert forbidden.isdisjoint(metric._labelnames)
