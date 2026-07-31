"""Run the local Phase 5B Temporal worker."""

import asyncio

from app.core.config import get_settings
from app.core.runtime_config import validate_runtime_settings
from app.observability.metrics import (
    WORKER_SERVICE,
    initialize_service_metrics,
    start_prometheus_metrics_server,
)
from app.temporal.worker import run

if __name__ == "__main__":
    settings = get_settings()
    issues = validate_runtime_settings(settings, service="worker")
    if issues:
        details = "; ".join(f"{item.field}: {item.reason}" for item in issues)
        raise SystemExit("invalid worker configuration: " + details)
    initialize_service_metrics(WORKER_SERVICE)
    if settings.prometheus_metrics_port:
        start_prometheus_metrics_server(settings.prometheus_metrics_port)
    asyncio.run(run())
