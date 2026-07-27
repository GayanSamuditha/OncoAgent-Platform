from datetime import datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

CriterionType = Literal["minimum_age", "maximum_age", "gender", "condition", "observation", "procedure", "medication", "diagnostic_report", "encounter_type", "date_window"]
CriterionStatus = Literal["verified", "not_verified", "conflicting", "missing_data", "not_applicable"]


class Criterion(BaseModel):
    criterion_id: str = Field(default_factory=lambda: "criterion")
    criterion_type: CriterionType
    clinical_concept: str | None = None
    code_system: str | None = None
    code: str | None = None
    operator: str = "contains"
    value: str | int | float | None = None
    unit: str | None = None
    date_window: dict[str, str] | None = None
    required: bool = True
    verification_tool: str = "auto"


class CohortPlan(BaseModel):
    objective: str
    dataset_id: str
    retrieval_query: str = Field(min_length=3, max_length=500)
    criteria: list[Criterion] = Field(min_length=1, max_length=10)
    retrieval_profile: Literal["medcpt", "bioclinicalbert", "postgres_fts"] = "medcpt"
    max_candidates: int = Field(default=20, ge=1, le=50)
    required_tools: list[str] = Field(min_length=1, max_length=20)
    verification_requirements: list[str] = Field(min_length=1)
    approval_required: Literal[True] = True
    plan_version: str = "phase3a-plan-v1"


class ActorContext(BaseModel):
    actor_id: str = Field(min_length=1, max_length=200)
    role: Literal["researcher", "reviewer", "admin"]


class RunCreateRequest(BaseModel):
    dataset_id: str
    request: str = Field(min_length=5, max_length=2000)
    criteria: list[Criterion] | None = Field(default=None, max_length=10)
    max_candidates: int = Field(default=20, ge=1, le=50)


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "reject", "request_changes", "cancel"]
    comment: str | None = Field(default=None, max_length=2000)


class WorkflowState(TypedDict, total=False):
    run_id: str
    thread_id: str
    actor_context: dict[str, Any]
    dataset_id: str
    original_request: str
    structured_input: dict[str, Any]
    structured_plan: dict[str, Any]
    plan_version: str
    planner_provider: str
    requested_criteria: list[dict[str, Any]]
    retrieval_policy: dict[str, Any]
    retrieval_attempts: list[dict[str, Any]]
    retrieval_fallbacks: list[dict[str, Any]]
    candidate_patient_ids: list[str]
    candidate_document_ids: list[str]
    candidate_results: list[dict[str, Any]]
    verification_results: list[dict[str, Any]]
    evidence_items: list[dict[str, Any]]
    included_patient_ids: list[str]
    excluded_patient_ids: list[str]
    policy_decisions: list[dict[str, Any]]
    approval_id: str
    approval_status: str
    approval_decision: dict[str, Any]
    cancellation_requested: bool
    warnings: list[str]
    errors: list[str]
    current_node: str
    run_status: str
    created_at: str
    updated_at: str
    final_result: dict[str, Any]


class EvidenceItem(BaseModel):
    patient_id: str
    criterion_id: str
    criterion_description: str
    verification_status: CriterionStatus
    structured_value: dict[str, Any] = Field(default_factory=dict)
    source_resource_type: str | None = None
    source_fhir_resource_id: str | None = None
    encounter_id: str | None = None
    effective_timestamp: datetime | None = None
    explanation: str
    verification_tool: str
    verification_tool_version: str
    dataset_id: str


class RunResponse(BaseModel):
    run_id: str
    thread_id: str
    status: str
    current_node: str
    created_at: datetime | None = None
    links: dict[str, str]
    dataset_id: str | None = None
    actor_id: str | None = None
    actor_role: str | None = None
    approval_id: str | None = None
    structured_plan: dict[str, Any] | None = None
    final_result: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    synthetic_data_notice: Literal["Synthetic Synthea data only."] = "Synthetic Synthea data only."


class ToolError(BaseModel):
    category: str
    message: str
    retryable: bool = False


class ToolDescriptor(BaseModel):
    name: str
    version: str
    description: str
    allowed_roles: list[str]
    read_only: bool
    timeout_seconds: int
    maximum_result_size: int
    retry_policy: dict[str, Any]
    audit_required: bool = True
