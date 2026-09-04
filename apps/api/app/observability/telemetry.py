"""OpenTelemetry setup with safe no-op behavior when disabled or unavailable."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.core.config import Settings

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
except ImportError:  # pragma: no cover - optional dependency boundary
    trace = None  # type: ignore[assignment]
    Resource = TracerProvider = BatchSpanProcessor = OTLPSpanExporter = None  # type: ignore[assignment,misc]


_configured = False
_enabled = False


def configure(settings: Settings) -> None:
    global _configured, _enabled
    if _configured:
        return
    _configured = True
    _enabled = bool(settings.observability_enabled and trace is not None)
    if not _enabled:
        return
    resource = Resource.create({"service.name": settings.otel_service_name, "deployment.environment": settings.environment})
    provider = TracerProvider(resource=resource)
    try:
        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True, timeout=3)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    except Exception:  # nosec B110
        # Tracing must not prevent application startup.
        pass
    trace.set_tracer_provider(provider)


def tracer(name: str = "oncoagent") -> Any:
    if trace is None:
        return None
    return trace.get_tracer(name)


@contextmanager
def span(name: str, settings: Settings | None = None, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
    if settings is not None:
        configure(settings)
    if trace is None or not _enabled:
        yield None
        return
    with tracer().start_as_current_span(name, attributes=attributes or {}) as current:
        yield current


def current_trace_context() -> dict[str, str | None]:
    if trace is None:
        return {"trace_id": None, "span_id": None}
    current = trace.get_current_span()
    context = current.get_span_context()
    if not context.is_valid:
        return {"trace_id": None, "span_id": None}
    return {"trace_id": format(context.trace_id, "032x"), "span_id": format(context.span_id, "016x")}


def observability_status(settings: Settings) -> dict[str, Any]:
    return {
        "enabled": settings.observability_enabled,
        "configured": _configured,
        "exporter_endpoint": settings.otel_exporter_otlp_endpoint if settings.observability_enabled else None,
        "service_name": settings.otel_service_name,
        "collector_unavailable_is_non_fatal": True,
        "synthetic_data_notice": "Synthetic Synthea data only.",
        "clinical_validation_notice": "Not clinically validated.",
    }
