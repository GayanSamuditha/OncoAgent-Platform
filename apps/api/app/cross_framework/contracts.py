from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class NormalizedEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_run_id: str
    scenario_id: str
    framework: Literal["langgraph", "crewai"]
    framework_version: str
    agent_or_workflow_version: str
    dataset_id: str
    final_status: str
    expected_outcome_match: bool
    candidate_count: int = Field(ge=0)
    included_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    required_criterion_coverage: float = Field(ge=0, le=1)
    evidence_provenance_coverage: float = Field(ge=0, le=1)
    unsupported_claim_count: int = Field(ge=0)
    tool_policy_violations: int = Field(ge=0)
    dataset_policy_violations: int = Field(ge=0)
    approval_required: bool
    approval_enforced: bool
    safety_rejection: bool
    total_latency_ms: float = Field(ge=0)
    model_latency_ms: float | None = Field(default=None, ge=0)
    tool_call_count: int = Field(ge=0)
    fallback_count: int = Field(ge=0)
    audit_event_count: int = Field(ge=0)
    process_recovery_capability: Literal["checkpoint_resume", "process_interrupted_only"]
    error_category: str | None = None
    limitations: list[str] = Field(default_factory=list)


class FrameworkAgent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    name: str
    framework: str
    framework_version: str
    owner: str
    role: str
    risk_tier: str
    supported_use_cases: list[str]
    prohibited_use_cases: list[str]
    dataset_permissions: list[str]
    tools: list[str]
    model_policy: dict[str, Any]
    approval_policy: dict[str, Any]
    recovery: dict[str, Any]
    status: str
    evaluation_summary: dict[str, Any]
    known_limitations: list[str]
