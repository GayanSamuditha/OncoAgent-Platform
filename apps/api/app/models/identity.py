"""Application identity, authorization, and access-decision records."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "identity_users"
    __table_args__ = (UniqueConstraint("issuer", "external_subject", name="uq_identity_subject"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    external_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_authenticated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Role(Base):
    __tablename__ = "identity_roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class Permission(Base):
    __tablename__ = "identity_permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class UserRole(Base):
    __tablename__ = "identity_user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_identity_user_role"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("identity_users.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[str] = mapped_column(
        ForeignKey("identity_roles.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RolePermission(Base):
    __tablename__ = "identity_role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_identity_role_permission"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    role_id: Mapped[str] = mapped_column(
        ForeignKey("identity_roles.id", ondelete="CASCADE"), index=True
    )
    permission_id: Mapped[str] = mapped_column(
        ForeignKey("identity_permissions.id", ondelete="CASCADE"), index=True
    )


class DatasetGrant(Base):
    __tablename__ = "identity_dataset_grants"
    __table_args__ = (UniqueConstraint("user_id", "dataset_id", name="uq_identity_dataset_grant"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("identity_users.id", ondelete="CASCADE"), index=True
    )
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    grant_type: Mapped[str] = mapped_column(String(40), default="synthetic_development")
    granted_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewerAssignment(Base):
    __tablename__ = "identity_reviewer_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "dataset_id", name="uq_identity_reviewer_assignment"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("identity_users.id", ondelete="CASCADE"), index=True
    )
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    review_type: Mapped[str] = mapped_column(String(80), default="synthetic_cohort")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccessDecisionAudit(Base):
    __tablename__ = "identity_access_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decision: Mapped[str] = mapped_column(String(30))
    reason_code: Mapped[str] = mapped_column(String(100))
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    canonical_digest: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    previous_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    integrity_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
