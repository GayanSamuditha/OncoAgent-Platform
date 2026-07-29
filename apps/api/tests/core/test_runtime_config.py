from app.core.config import Settings
from app.core.runtime_config import validate_runtime_settings


def test_local_defaults_are_valid_for_api() -> None:
    assert validate_runtime_settings(Settings(), service="api") == []


def test_non_local_placeholder_secret_is_rejected() -> None:
    settings = Settings(environment="development")
    fields = {issue.field for issue in validate_runtime_settings(settings)}
    assert "IDENTITY_SIGNING_SECRET" in fields


def test_temporal_worker_requires_explicit_temporal_mode() -> None:
    settings = Settings(crewai_execution_mode="legacy")
    fields = {issue.field for issue in validate_runtime_settings(settings, service="worker")}
    assert "CREWAI_EXECUTION_MODE" in fields


def test_fault_injection_is_rejected_outside_local() -> None:
    settings = Settings(environment="development", temporal_dev_fault_stage="brief")
    fields = {issue.field for issue in validate_runtime_settings(settings)}
    assert "TEMPORAL_DEV_FAULT_*" in fields
