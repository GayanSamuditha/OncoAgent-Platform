"""Strict contracts exchanged between CrewAI tasks and the platform API."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


CriterionType = Literal[
    "minimum_age",
    "maximum_age",
    "gender",
    "condition",
    "observation",
    "procedure",
    "medication",
    "diagnostic_report",
    "encounter_type",
    "date_window",
]


class Criterion(Strict):
    criterion_type: CriterionType
    clinical_concept: str | None = None
    code_system: str | None = None
    code: str | None = None
    operator: str = "contains"
    value: str | int | float | None = None
    unit: str | None = None
    date_window: dict[str, str] | None = None
    required: bool = True


class ActorContext(Strict):
    actor_id: str = Field(min_length=1, max_length=200)
    actor_role: Literal["researcher", "reviewer", "admin"]


class CrewRunRequest(Strict):
    dataset_id: str = Field(min_length=1, max_length=36)
    research_question: str = Field(min_length=5, max_length=2000)
    structured_criteria: list[Criterion] = Field(min_length=1, max_length=10)
    maximum_candidates: int = Field(default=20, ge=1, le=50)
    retrieval_profile: Literal["medcpt", "bioclinicalbert", "postgres_fts"] = "medcpt"
    model_profile: Literal["automatic", "llama3.2:3b", "qwen3:8b"] = "automatic"
    actor_context: ActorContext
    correlation_id: str | None = Field(default=None, max_length=100)
    idempotency_key: str | None = Field(default=None, max_length=200)


class CrewReviewRequest(Strict):
    decision: Literal["accept_for_synthetic_research", "reject", "request_changes", "cancel"]
    comment: str | None = Field(default=None, max_length=2000)


class CandidateDiscoveryResult(Strict):
    run_id: str
    dataset_id: str
    normalized_query: str
    retrieval_profile_requested: str
    retrieval_provider_used: str
    fallback_history: list[dict[str, Any]] = []
    candidate_patient_ids: list[str] = []
    candidate_document_ids: list[str] = []
    candidate_encounter_ids: list[str] = []
    search_evidence: list[dict[str, Any]] = []
    warnings: list[str] = []
    limitations: list[str] = []


class StructuredEvidenceResult(Strict):
    run_id: str
    dataset_id: str
    patient_evidence: list[dict[str, Any]] = []
    criteria_checked: list[str] = []
    missing_data: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    tool_calls: list[str] = []
    source_resource_ids: list[str] = []
    warnings: list[str] = []


class EligibilityReviewResult(Strict):
    run_id: str
    dataset_id: str
    criteria: list[Criterion]
    proposed_included_patients: list[str] = []
    proposed_excluded_patients: list[str] = []
    unresolved_patients: list[str] = []
    patient_criterion_results: list[dict[str, Any]] = []
    provenance_coverage: float = Field(ge=0, le=1)
    unsupported_claims_removed: list[str] = []
    warnings: list[str] = []
    review_required: Literal[True] = True


class SyntheticResearchBrief(Strict):
    run_id: str
    dataset_id: str
    research_question: str
    methods_summary: str
    retrieval_summary: dict[str, Any]
    candidate_count: int = Field(ge=0)
    proposed_included_count: int = Field(ge=0)
    proposed_excluded_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    patient_summaries: list[dict[str, Any]] = []
    evidence_limitations: list[str] = []
    provenance_summary: dict[str, Any] = {}
    model_lineage: dict[str, Any] = {}
    mcp_lineage: dict[str, Any] = {}
    synthetic_data_notice: Literal["Only synthetic Synthea data was used."] = (
        "Only synthetic Synthea data was used."
    )
    clinical_validation_notice: Literal["This result is not clinically validated."] = (
        "This result is not clinically validated."
    )
    review_status: Literal["awaiting_human_review"] = "awaiting_human_review"
