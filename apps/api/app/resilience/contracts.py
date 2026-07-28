"""Machine-readable resilience certification contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CertificationScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    description: str
    prerequisites: list[str] = []
    injected_failure: str | None = None
    expected_retry_classification: Literal["retryable", "non_retryable", "none"]
    expected_activity_attempts: int | None = Field(default=None, ge=1)
    expected_recovery_boundary: str
    expected_terminal_status: str
    expected_business_record_counts: dict[str, int]
    expected_audit_result: str
    expected_trace_result: str
    cleanup_procedure: str


class CertificationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    certification_id: str
    scenario_id: str
    application_run_id: str | None = None
    temporal_workflow_id: str | None = None
    temporal_run_id: str | None = None
    activity_name: str | None = None
    activity_attempts: list[int] = []
    failure_category: str | None = None
    retry_classification: str = "none"
    recovery_boundary: str = "not_applicable"
    final_status: str
    duplicate_record_counts: dict[str, int] = {}
    audit_result: str
    trace_result: str
    redaction_result: str
    duration_ms: float | None = None
    heartbeat_observed: bool = False
    cancellation_observed: bool = False
    passed: bool
    limitations: list[str] = []


class CertificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    certification_id: str
    report_version: str = "phase5c-v1"
    scenario_registry_version: str
    platform_version: str
    environment: str
    temporal_server_version: str
    temporal_sdk_version: str
    migration_revision: str
    generated_at: str
    scenarios: list[CertificationObservation]
    scorecard: dict[str, dict[str, object]]
    overall_status: Literal["passed", "failed", "incomplete"]
    limitations: list[str] = []

