"""Application records for the downstream CrewAI research client."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CrewRun(Base):
    __tablename__ = "crew_runs"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_crew_runs_idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    correlation_id: Mapped[str] = mapped_column(String(36), index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(200))
    actor_role: Mapped[str] = mapped_column(String(40))
    mcp_client_id: Mapped[str] = mapped_column(String(120))
    crew_name: Mapped[str] = mapped_column(String(120), default="OncologyResearchCrew")
    crew_version: Mapped[str] = mapped_column(String(40), default="phase4b-v1")
    crewai_version: Mapped[str] = mapped_column(String(40), default="unknown")
    process_type: Mapped[str] = mapped_column(String(30), default="sequential")
    model_tag: Mapped[str] = mapped_column(String(120))
    model_digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    current_task: Mapped[str | None] = mapped_column(String(80), nullable=True)
    research_question: Mapped[str] = mapped_column(Text)
    structured_criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    sanitized_input: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    output_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    span_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    temporal_workflow_id: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True, index=True)
    temporal_run_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    temporal_namespace: Mapped[str | None] = mapped_column(String(100), nullable=True)
    temporal_task_queue: Mapped[str | None] = mapped_column(String(120), nullable=True)
    temporal_execution_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    temporal_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    temporal_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    temporal_last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    temporal_current_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    temporal_activity_attempt: Mapped[int | None] = mapped_column(nullable=True)
    temporal_failure_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    temporal_failure_message_redacted: Mapped[str | None] = mapped_column(Text, nullable=True)
    temporal_execution_mode: Mapped[str] = mapped_column(String(30), default="legacy", nullable=False)
    temporal_correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)


class CrewAgent(Base):
    __tablename__ = "crew_agents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    crew_run_id: Mapped[str] = mapped_column(
        ForeignKey("crew_runs.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(40))
    allowed_tools: Mapped[list[str]] = mapped_column(JSONB, default=list)


class CrewTask(Base):
    __tablename__ = "crew_tasks"
    __table_args__ = (UniqueConstraint("crew_run_id", "task_name", name="uq_crew_tasks_run_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    crew_run_id: Mapped[str] = mapped_column(
        ForeignKey("crew_runs.id", ondelete="CASCADE"), index=True
    )
    task_name: Mapped[str] = mapped_column(String(100))
    task_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30))
    agent_role: Mapped[str] = mapped_column(String(100))
    output_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    latency_ms: Mapped[float | None] = mapped_column(nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    span_id: Mapped[str | None] = mapped_column(String(16), nullable=True)


class CrewEvent(Base):
    __tablename__ = "crew_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    crew_run_id: Mapped[str] = mapped_column(
        ForeignKey("crew_runs.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    task_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    span_id: Mapped[str | None] = mapped_column(String(16), nullable=True)


class CrewOutput(Base):
    __tablename__ = "crew_outputs"
    __table_args__ = (
        UniqueConstraint("crew_run_id", "output_type", name="uq_crew_outputs_run_type"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    crew_run_id: Mapped[str] = mapped_column(
        ForeignKey("crew_runs.id", ondelete="CASCADE"), index=True
    )
    output_type: Mapped[str] = mapped_column(String(60))
    schema_version: Mapped[str] = mapped_column(String(40))
    output_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CrewReview(Base):
    __tablename__ = "crew_reviews"
    __table_args__ = (UniqueConstraint("crew_run_id", name="uq_crew_reviews_run"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    crew_run_id: Mapped[str] = mapped_column(
        ForeignKey("crew_runs.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="pending")
    reviewer_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewer_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(50), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CrewLineage(Base):
    __tablename__ = "crew_lineage"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    crew_run_id: Mapped[str] = mapped_column(
        ForeignKey("crew_runs.id", ondelete="CASCADE"), index=True
    )
    config_version: Mapped[str] = mapped_column(String(40))
    config_hash: Mapped[str] = mapped_column(String(64))
    mcp_protocol_version: Mapped[str] = mapped_column(String(40))
    mcp_server_version: Mapped[str] = mapped_column(String(40))
    mcp_request_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    mcp_request_context: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    tool_names: Mapped[list[str]] = mapped_column(JSONB, default=list)
    retrieval_lineage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    token_usage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
