"""Sanitized security readiness persistence."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SecurityAssessmentRecord(Base):
    __tablename__ = "security_assessments"
    __table_args__ = (UniqueConstraint("assessment_id", name="uq_security_assessment_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(String(120), index=True)
    policy_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), index=True)
    artifact_hash: Mapped[str] = mapped_column(String(64))
    report_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    findings_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    gates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    limitations: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SecurityFindingRecord(Base):
    __tablename__ = "security_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("security_assessments.id", ondelete="CASCADE"), index=True
    )
    finding_id: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(30), index=True)
    state: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(240))
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)


class SecurityRetentionRuleRecord(Base):
    __tablename__ = "security_retention_rules"
    __table_args__ = (UniqueConstraint("rule_id", name="uq_security_retention_rule"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(100))
    duration_days: Mapped[int | None] = mapped_column(nullable=True)
    rationale: Mapped[str] = mapped_column(Text)
    deletion_method: Mapped[str] = mapped_column(String(200))
    exception_behavior: Mapped[str] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(String(120))
    review_date: Mapped[date] = mapped_column(Date)
