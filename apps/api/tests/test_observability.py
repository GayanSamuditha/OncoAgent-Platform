from app.core.config import Settings
from app.observability.metrics import prometheus_payload
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
