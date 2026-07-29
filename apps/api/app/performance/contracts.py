"""Versioned, sanitized contracts for local performance measurements."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "7B.2"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class HardwareProfile(StrictModel):
    platform: str
    architecture: str
    cpu_count: int = Field(ge=1, le=256)
    memory_gb: float = Field(gt=0, le=2048)
    docker_configuration: str = "local-development"


class VersionManifest(StrictModel):
    application_commit: str = "unknown"
    dataset: str = "synthetic"
    dataset_id: str | None = None
    model: str | None = None
    model_digest: str | None = None
    prompt_version: str | None = None
    retrieval_profile: str | None = None
    workflow_version: str | None = None
    mcp_registry_version: str | None = None
    temporal_configuration: str | None = None
    concurrency_configuration: str | None = None
    hardware: HardwareProfile


class WorkloadProfile(StrictModel):
    profile_id: str
    version: str = CONTRACT_VERSION
    description: str
    concurrency: int = Field(ge=1, le=32)
    request_count: int = Field(ge=1, le=1000)
    warmup_count: int = Field(ge=0, le=100)
    timeout_seconds: float = Field(gt=0, le=600)
    request_mix: dict[str, float] = Field(default_factory=dict)
    dataset_id: str | None = None
    model_profile: str | None = None
    expected_status_classes: list[str] = Field(default_factory=lambda: ["2xx"])
    max_memory_gb: float = Field(gt=0, le=64)
    cleanup: str = "no destructive cleanup"


class PerformanceObservation(StrictModel):
    operation: str
    status_class: str
    duration_ms: float = Field(ge=0)
    queue_wait_ms: float = Field(default=0, ge=0)
    error_category: str | None = None
    correlation_present: bool = True


class ServiceMetric(StrictModel):
    name: str
    value: float | None
    unit: str
    sample_size: int = Field(ge=0)
    denominator: int | None = Field(default=None, ge=0)
    status: Literal["measured", "not_applicable", "not_evaluable"]
    definition: str


class SLOResult(StrictModel):
    name: str
    value: float | None
    threshold: float | None
    unit: str
    status: Literal["pass", "fail", "not_applicable", "not_evaluable"]
    blocking: bool
    sample_size: int = Field(ge=0)
    reason: str


class BottleneckFinding(StrictModel):
    category: str
    severity: Literal["info", "warning", "high"]
    evidence: str
    limitation: str


class PerformanceExecution(StrictModel):
    execution_id: str
    plan_id: str
    profile_id: str
    status: Literal["created", "running", "completed", "failed", "cancelled", "not_evaluable"]
    adapter: str = "unknown"
    supported: bool = True
    not_evaluable_reason: str | None = None
    operation_count: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    expected_denial_count: int = Field(default=0, ge=0)
    unexpected_failure_count: int = Field(default=0, ge=0)
    timeout_count: int = Field(default=0, ge=0)
    active_concurrency: int = Field(default=0, ge=0)
    details: dict[str, object] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    observations: list[PerformanceObservation] = Field(default_factory=list)
    metrics: list[ServiceMetric] = Field(default_factory=list)
    slos: list[SLOResult] = Field(default_factory=list)
    findings: list[BottleneckFinding] = Field(default_factory=list)
    manifest: VersionManifest
    report_reference: str | None = None


class PerformanceReport(StrictModel):
    report_version: str = CONTRACT_VERSION
    execution: PerformanceExecution
    notice: str = (
        "Synthetic development performance evaluation; local hardware-specific; "
        "not clinically validated or production capacity evidence."
    )
