"""Bounded local-only Temporal fault controls used by live validation."""

from typing import Any

from app.core.config import Settings

ALLOWED_FAULTS = {
    "ollama_unavailable",
    "mcp_transport_failure",
    "postgresql_transient_failure",
    "worker_interrupted",
    "bounded_timeout",
}


def configured_fault(settings: Settings, stage: str, attempt: int) -> str | None:
    """Return a one-shot allowlisted fault only in local/test environments."""
    if settings.environment not in {"local", "test"}:
        return None
    if settings.temporal_dev_fault_stage != stage:
        return None
    if settings.temporal_dev_fault_category not in ALLOWED_FAULTS:
        return None
    if attempt > settings.temporal_dev_fault_attempts:
        return None
    return settings.temporal_dev_fault_category


def safe_progress(stage: str, progress: str, task_index: int = 0) -> dict[str, Any]:
    return {"stage": stage, "progress": progress, "task_index": task_index}
