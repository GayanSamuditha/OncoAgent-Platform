from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SafetyOutcome(StrEnum):
    ACCEPTED_SAFE = "accepted_safe"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    NEEDS_CLARIFICATION_SAFE = "needs_clarification_safe"
    REJECTED_UNSAFE = "rejected_unsafe"
    REJECTED_UNSUPPORTED = "rejected_unsupported"
    POLICY_VIOLATION_PREVENTED = "policy_violation_prevented"
    FAILED_SAFE = "failed_safe"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class ProvenanceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_evidence_count: int = Field(ge=0)
    valid_provenance_count: int = Field(ge=0)
    missing_provenance_count: int = Field(ge=0)
    invalid_references: list[str] = []
    affected_patient_ids: list[str] = []
    affected_criterion_ids: list[str] = []
    coverage: float = Field(ge=0, le=1)
    defects: list[str] = []


class AuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    complete: bool
    missing_events: list[str] = []
    order_violations: list[str] = []
    unclosed_tasks: list[str] = []
    orphan_mcp_request_ids: list[str] = []
    defects: list[str] = []


class SafetyClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operational_status: str
    safety_outcome: SafetyOutcome
    unsafe_instruction_present: bool
    unsafe_instruction_executed: bool
    tools_executed: bool
    clinical_data_accessed: bool
    human_review_required: bool
    human_review_enforced: bool
    responsible_policy_rule: str


class GovernanceGate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: float
    threshold: float
    passed: bool
    sample_size: int = Field(ge=0)
    definition: str
    limitations: list[str] = []


class GovernanceScorecard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    framework: Literal["langgraph", "crewai"]
    gates: list[GovernanceGate]
    failed_gates: list[str]
    limitations: list[str] = []


class MismatchAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    expected_outcome: str
    operational_result: str
    safety_outcome: SafetyOutcome
    tools_executed: bool
    clinical_data_access: bool
    evidence_result: str
    provenance_result: str
    human_review_result: str
    mismatch_category: str
    root_cause: str
    safe_behavior: bool
    code_changed: bool = False
