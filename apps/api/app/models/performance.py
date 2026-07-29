"""Sanitized persistence for bounded performance and reliability runs."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PerformanceTestPlanRecord(Base):
    __tablename__ = "performance_test_plans"
    __table_args__ = (UniqueConstraint("plan_id", "version", name="uq_performance_plan_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)
    profile_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PerformanceExecutionRecord(Base):
    __tablename__ = "performance_executions"
    __table_args__ = (UniqueConstraint("execution_id", name="uq_performance_execution_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(120), index=True)
    plan_id: Mapped[str] = mapped_column(String(120), index=True)
    profile_id: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    dataset_id: Mapped[str | None] = mapped_column(
        ForeignKey("datasets.id"), nullable=True, index=True
    )
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    report_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PerformanceMetricRecord(Base):
    __tablename__ = "performance_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    value: Mapped[float | None] = mapped_column(nullable=True)
    unit: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30))
    sample_size: Mapped[int] = mapped_column(default=0)
    denominator: Mapped[int | None] = mapped_column(nullable=True)
    definition: Mapped[str] = mapped_column(Text)


class PerformanceSLORecord(Base):
    __tablename__ = "performance_slos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    value: Mapped[float | None] = mapped_column(nullable=True)
    threshold: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(30))
    blocking: Mapped[bool] = mapped_column(default=False)
    sample_size: Mapped[int] = mapped_column(default=0)
    reason: Mapped[str] = mapped_column(Text)


class PerformanceFindingRecord(Base):
    __tablename__ = "performance_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(30))
    evidence: Mapped[str] = mapped_column(Text)
    limitation: Mapped[str] = mapped_column(Text)
