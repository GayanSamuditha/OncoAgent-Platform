"""Bounded serializable contracts crossing the Temporal boundary."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TemporalCrewWorkflowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=36)
    request: dict[str, Any]
    temporal_workflow_id: str = Field(min_length=1, max_length=200)
    correlation_id: str = Field(min_length=1, max_length=100)


class TemporalReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["accept_for_synthetic_research", "reject", "request_changes", "cancel"]
    comment: str | None = Field(default=None, max_length=2000)
    reviewer_id: str = Field(min_length=1, max_length=200)
    reviewer_role: Literal["reviewer", "admin"]


class TemporalWorkflowStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    workflow_id: str
    temporal_run_id: str | None = None
    status: str
    current_stage: str
    activity_attempt: int
    waiting_for_review: bool
    review_decision_received: bool = False
    cancellation_requested: bool
    last_safe_progress: dict[str, str] = Field(default_factory=dict)
