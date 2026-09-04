"""Versioned, sanitized security evidence contracts."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

SecuritySeverity = Literal["informational", "low", "medium", "high", "critical"]
FindingState = Literal["open", "accepted_risk", "remediated", "false_positive", "not_applicable"]
EvidenceStatus = Literal["measured", "passed", "failed", "not_evaluable", "error", "not_applicable"]


class SecurityPolicy(BaseModel):
    version: str
    name: str
    development_only: bool = True
    blocking_gate_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class TrustBoundary(BaseModel):
    boundary_id: str
    source: str
    destination: str
    controls: list[str] = Field(default_factory=list)


class SecurityControl(BaseModel):
    control_id: str
    family: str
    title: str
    owner: str
    implementation_state: Literal["implemented", "partial", "planned", "accepted_limitation"]


class SecurityFinding(BaseModel):
    finding_id: str
    category: str
    severity: SecuritySeverity
    state: FindingState
    title: str
    location: str | None = None
    reason: str
    owner: str | None = None
    expires_on: date | None = None
    compensating_control: str | None = None
    approval_identity: str | None = None


class SecurityControlResult(BaseModel):
    control_id: str
    family: str
    title: str
    status: EvidenceStatus
    evidence_reference: str | None = None
    limitation: str | None = None


class VulnerabilityObservation(BaseModel):
    scanner: str
    status: EvidenceStatus
    severity_counts: dict[SecuritySeverity, int] = Field(default_factory=dict)
    artifact_reference: str | None = None
    limitation: str | None = None


class SecretScanObservation(BaseModel):
    scanner: str
    status: EvidenceStatus
    finding_count: int = Field(ge=0)
    finding_types: list[str] = Field(default_factory=list)
    limitation: str | None = None


class DependencyScanObservation(VulnerabilityObservation):
    ecosystem: Literal["python", "node", "container"]


class PrivacyObservation(BaseModel):
    scanner: str
    status: EvidenceStatus
    violation_count: int = Field(ge=0)
    categories: list[str] = Field(default_factory=list)
    limitation: str | None = None


class IncidentReadinessCheck(BaseModel):
    scenario: str
    status: EvidenceStatus
    detection_signal: str
    containment: str
    limitation: str | None = None


class SecurityAssessment(BaseModel):
    assessment_id: str
    policy_version: str
    status: Literal["passed", "failed", "not_evaluable", "error"]
    created_at: datetime
    control_results: list[SecurityControlResult] = Field(default_factory=list)
    findings: list[SecurityFinding] = Field(default_factory=list)
    artifact_hash: str | None = None
    report_reference: str | None = None
    limitations: list[str] = Field(default_factory=list)


class RetentionRule(BaseModel):
    rule_id: str
    category: str
    duration_days: int | None
    rationale: str
    deletion_method: str
    exception_behavior: str
    owner: str
    review_date: date


class AuditIntegrityResult(BaseModel):
    status: Literal["verified", "legacy_unverified", "failed", "not_evaluable", "error"]
    checked_records: int
    legacy_records: int
    changed_records: list[str] = Field(default_factory=list)
    missing_records: list[str] = Field(default_factory=list)
    inserted_records: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class SecurityReleaseEvidence(BaseModel):
    version: str
    assessment_id: str
    metrics: dict[str, float | None]
    metric_status: dict[str, EvidenceStatus]
    artifact_hash: str
    limitations: list[str] = Field(default_factory=list)


class ThreatModel(BaseModel):
    version: str
    actors: list[str]
    assets: list[str]
    trust_boundaries: list[str]
    controls: dict[str, str]
