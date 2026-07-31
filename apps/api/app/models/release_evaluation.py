"""Persisted release-candidate evaluation summaries and gate decisions."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReleaseCandidateRecord(Base):
    __tablename__ = "release_candidates"
    __table_args__ = (
        UniqueConstraint("candidate_id", "candidate_version", name="uq_release_candidate_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(120), index=True)
    candidate_version: Mapped[str] = mapped_column(String(80))
    baseline_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    baseline_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    evaluation_suite_version: Mapped[str] = mapped_column(String(80))
    artifact_versions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReleaseEvaluationExecution(Base):
    __tablename__ = "release_evaluation_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("release_candidates.id"), index=True)
    decision: Mapped[str] = mapped_column(String(50), index=True)
    report_version: Mapped[str] = mapped_column(String(80))
    evaluation_input_hash: Mapped[str] = mapped_column(String(64), index=True)
    baseline_reference: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    framework_results: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    limitations: Mapped[list[str]] = mapped_column(JSONB, default=list)
    report_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReleaseMetricResult(Base):
    __tablename__ = "release_metric_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("release_evaluation_executions.id", ondelete="CASCADE"), index=True
    )
    metric_name: Mapped[str] = mapped_column(String(160), index=True)
    value: Mapped[float | None] = mapped_column(nullable=True)
    baseline_value: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(30))
    sample_size: Mapped[int] = mapped_column(default=0)
    denominator: Mapped[int | None] = mapped_column(nullable=True)
    definition: Mapped[str] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(String(20))
    delta: Mapped[float | None] = mapped_column(nullable=True)


class ReleaseGateResult(Base):
    __tablename__ = "release_gate_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("release_evaluation_executions.id", ondelete="CASCADE"), index=True
    )
    gate_name: Mapped[str] = mapped_column(String(120), index=True)
    metric_name: Mapped[str] = mapped_column(String(160))
    value: Mapped[float | None] = mapped_column(nullable=True)
    threshold: Mapped[float] = mapped_column()
    status: Mapped[str] = mapped_column(String(30))
    passed: Mapped[bool] = mapped_column()
    blocking: Mapped[bool] = mapped_column(default=True)
    sample_size: Mapped[int] = mapped_column(default=0)
    reason: Mapped[str] = mapped_column(Text)


class ReleaseDecision(Base):
    __tablename__ = "release_decisions"
    __table_args__ = (UniqueConstraint("evaluation_id", name="uq_release_decision_evaluation"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("release_evaluation_executions.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(50))
    blocking_reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
