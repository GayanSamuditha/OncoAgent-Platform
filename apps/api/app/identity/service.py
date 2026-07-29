"""Centralized identity, permission, dataset, and reviewer policy."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import jwt
from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.identity import (
    AccessDecisionAudit,
    DatasetGrant,
    ReviewerAssignment,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.observability.metrics import (
    IDENTITY_AUTHZ,
    IDENTITY_DATASET,
    IDENTITY_REVIEW,
    SECURITY_AUTH_FAILURES,
    SECURITY_AUTHZ_DENIALS,
    SECURITY_DATASET_DENIALS,
    SECURITY_SELF_APPROVAL_DENIALS,
    observe,
)
from app.observability.telemetry import current_trace_context
from app.security.audit_integrity import INTEGRITY_VERSION, digest_for

LOCAL_USERS: dict[str, tuple[str, str]] = {
    "researcher-console": ("researcher", "Synthetic Researcher"),
    "reviewer-console": ("reviewer", "Synthetic Reviewer"),
    "governance-console": ("governance_officer", "Governance Officer"),
    "operator-console": ("platform_operator", "Platform Operator"),
    "auditor-console": ("auditor", "Audit Reader"),
    "admin-console": ("administrator", "Local Administrator"),
}


@dataclass(frozen=True)
class AuthenticatedUser:
    internal_id: str
    subject: str
    issuer: str
    display_name: str
    email: str | None
    role: str
    permissions: frozenset[str]
    dataset_ids: frozenset[str]
    enabled: bool = True

    @property
    def actor_id(self) -> str:
        return self.subject


def configured_local_users(settings: Settings) -> dict[str, tuple[str, str]]:
    if not settings.identity_dev_users:
        return LOCAL_USERS
    try:
        values = json.loads(settings.identity_dev_users)
    except json.JSONDecodeError as exc:
        raise RuntimeError("IDENTITY_DEV_USERS must be valid local JSON") from exc
    result: dict[str, tuple[str, str]] = {}
    for key, value in values.items():
        if isinstance(value, dict) and value.get("role") in settings.identity_allowed_roles:
            result[key] = (str(value["role"]), str(value.get("display_name", key)))
    return result


def _role_permissions(session: Session, role_name: str) -> frozenset[str]:
    rows = session.execute(
        select(RolePermission)
        .join(Role, Role.id == RolePermission.role_id)
        .where(Role.name == role_name)
    ).scalars()
    # Permission names are loaded through one explicit query to keep policy centralized.
    from app.models.identity import Permission

    permission_ids = [row.permission_id for row in rows]
    if not permission_ids:
        return frozenset()
    return frozenset(
        session.scalars(select(Permission.name).where(Permission.id.in_(permission_ids))).all()
    )


def ensure_local_user(session: Session, settings: Settings, user_key: str) -> AuthenticatedUser:
    users = configured_local_users(settings)
    profile = users.get(user_key)
    if profile is None:
        raise HTTPException(status_code=401, detail="unknown local identity")
    role_name, display_name = profile
    user = session.scalar(
        select(User).where(
            User.issuer == settings.identity_issuer, User.external_subject == user_key
        )
    )
    if user is None:
        user = User(
            id=str(uuid4()),
            external_subject=user_key,
            issuer=settings.identity_issuer,
            display_name=display_name,
        )
        session.add(user)
        session.flush()
    role = session.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        raise HTTPException(status_code=503, detail="identity roles are not initialized")
    if (
        session.scalar(
            select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
        )
        is None
    ):
        session.add(UserRole(id=str(uuid4()), user_id=user.id, role_id=role.id))
    # Local development grants are explicit persisted grants, scoped to current synthetic datasets.
    from app.models.ingestion import Dataset

    datasets = list(session.scalars(select(Dataset)))
    for dataset in datasets:
        grant = session.scalar(
            select(DatasetGrant).where(
                DatasetGrant.user_id == user.id, DatasetGrant.dataset_id == dataset.id
            )
        )
        if grant is None:
            session.add(
                DatasetGrant(
                    id=str(uuid4()),
                    user_id=user.id,
                    dataset_id=dataset.id,
                    granted_by="local-bootstrap",
                )
            )
        # Administrators manage identity and operations; they are not made
        # reviewers implicitly.  Review authority requires an explicit
        # reviewer role, dataset grant, and reviewer assignment.
        if role_name == "reviewer":
            assignment = session.scalar(
                select(ReviewerAssignment).where(
                    ReviewerAssignment.user_id == user.id,
                    ReviewerAssignment.dataset_id == dataset.id,
                )
            )
            if assignment is None:
                session.add(
                    ReviewerAssignment(id=str(uuid4()), user_id=user.id, dataset_id=dataset.id)
                )
    user.last_authenticated_at = datetime.now(UTC)
    session.commit()
    session.refresh(user)
    return _to_auth_user(session, user, role_name)


def _to_auth_user(session: Session, user: User, role_name: str | None = None) -> AuthenticatedUser:
    role = role_name or session.scalar(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    )
    if not role:
        raise HTTPException(status_code=403, detail="identity has no active role")
    permissions = _role_permissions(session, role)
    dataset_ids = frozenset(
        session.scalars(
            select(DatasetGrant.dataset_id).where(
                DatasetGrant.user_id == user.id, DatasetGrant.enabled.is_(True)
            )
        ).all()
    )
    return AuthenticatedUser(
        user.id,
        user.external_subject,
        user.issuer,
        user.display_name,
        user.email,
        role,
        permissions,
        dataset_ids,
        user.enabled,
    )


def issue_session(user: AuthenticatedUser, settings: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": settings.identity_issuer,
            "aud": settings.identity_audience,
            "sub": user.subject,
            "iat": now,
            "exp": now.timestamp() + settings.identity_session_ttl_seconds,
            "name": user.display_name,
        },
        settings.identity_signing_secret,
        algorithm="HS256",
    )


def _token_from_request(request: Request, settings: Settings) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.cookies.get(settings.identity_session_cookie)


def authenticate_request(
    request: Request, session: Session, settings: Settings
) -> AuthenticatedUser:
    token = _token_from_request(request, settings)
    if not token:
        observe(SECURITY_AUTH_FAILURES, labels={"reason": "missing_token"})
        raise HTTPException(status_code=401, detail="authentication required")
    try:
        claims = jwt.decode(
            token,
            settings.identity_signing_secret,
            algorithms=["HS256"],
            audience=settings.identity_audience,
            issuer=settings.identity_issuer,
            options={"require": ["iss", "aud", "sub", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        observe(SECURITY_AUTH_FAILURES, labels={"reason": "expired"})
        raise HTTPException(status_code=401, detail="session expired") from exc
    except jwt.InvalidTokenError as exc:
        observe(SECURITY_AUTH_FAILURES, labels={"reason": "invalid"})
        raise HTTPException(status_code=401, detail="invalid session") from exc
    user = session.scalar(
        select(User).where(
            User.issuer == settings.identity_issuer, User.external_subject == str(claims["sub"])
        )
    )
    if user is None or not user.enabled:
        observe(SECURITY_AUTH_FAILURES, labels={"reason": "disabled_or_unknown"})
        raise HTTPException(status_code=401, detail="identity is disabled or unknown")
    return _to_auth_user(session, user)


def record_access(
    session: Session,
    user: AuthenticatedUser | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    decision: str,
    reason_code: str,
    correlation_id: str | None = None,
) -> None:
    trace = current_trace_context()
    previous = (
        session.scalar(
            select(AccessDecisionAudit)
            .where(AccessDecisionAudit.canonical_digest.is_not(None))
            .order_by(AccessDecisionAudit.created_at.desc(), AccessDecisionAudit.id.desc())
        )
        if hasattr(session, "scalar")
        else None
    )
    item = AccessDecisionAudit(
        id=str(uuid4()),
        actor_id=user.internal_id if user else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        decision=decision,
        reason_code=reason_code,
        correlation_id=correlation_id,
        trace_id=trace.get("trace_id"),
        details={},
        previous_digest=previous.canonical_digest if previous else None,
        integrity_version=INTEGRITY_VERSION,
    )
    session.add(item)
    if hasattr(session, "flush"):
        session.flush()
        item.canonical_digest = digest_for(item)
    session.commit()


def require_permission(
    user: AuthenticatedUser, permission: str, session: Session, *, action: str = "authorization"
) -> None:
    if permission not in user.permissions:
        observe(SECURITY_AUTHZ_DENIALS, labels={"reason": "permission_denied"})
        observe(IDENTITY_AUTHZ, labels={"decision": "deny", "reason": "permission_denied"})
        record_access(session, user, action, "permission", permission, "deny", "permission_denied")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
    observe(IDENTITY_AUTHZ, labels={"decision": "allow", "reason": "permission_granted"})


def require_dataset(
    user: AuthenticatedUser, dataset_id: str, session: Session, *, action: str = "dataset_access"
) -> None:
    from app.models.ingestion import Dataset

    if session.get(Dataset, dataset_id) is None:
        observe(IDENTITY_DATASET, labels={"decision": "deny"})
        record_access(session, user, action, "dataset", dataset_id, "deny", "dataset_not_found")
        raise HTTPException(status_code=404, detail="dataset not found")
    if "dataset:use" not in user.permissions or dataset_id not in user.dataset_ids:
        observe(SECURITY_DATASET_DENIALS)
        observe(IDENTITY_DATASET, labels={"decision": "deny"})
        record_access(session, user, action, "dataset", dataset_id, "deny", "dataset_denied")
        raise HTTPException(status_code=403, detail="dataset access denied")
    record_access(session, user, action, "dataset", dataset_id, "allow", "dataset_granted")
    observe(IDENTITY_DATASET, labels={"decision": "allow"})


def require_reviewer(
    user: AuthenticatedUser,
    dataset_id: str,
    session: Session,
    creator_id: str,
    *,
    action: str = "review_decision",
) -> None:
    """Authorize an assigned reviewer without applying run ownership rules.

    Review authority is deliberately independent from workflow read access:
    an assigned reviewer may inspect and decide a pending review for a run
    created by another user, while ordinary run endpoints still use their
    ownership/``workflow:read-all`` policy.
    """
    if not user.enabled:
        record_access(session, user, action, "review", None, "deny", "disabled_user")
        raise HTTPException(status_code=403, detail="reviewer account is disabled")
    if user.role != "reviewer":
        record_access(session, user, action, "review", None, "deny", "reviewer_role_required")
        raise HTTPException(status_code=403, detail="reviewer role is required")
    require_permission(user, "review:decide", session, action=action)
    require_dataset(user, dataset_id, session, action="review_dataset_access")
    if user.internal_id == creator_id or user.subject == creator_id:
        observe(SECURITY_SELF_APPROVAL_DENIALS)
        record_access(session, user, action, "review", None, "deny", "self_approval")
        raise HTTPException(status_code=403, detail="researcher cannot approve their own run")
    assignment = session.scalar(
        select(ReviewerAssignment).where(
            ReviewerAssignment.user_id == user.internal_id,
            ReviewerAssignment.dataset_id == dataset_id,
            ReviewerAssignment.enabled.is_(True),
        )
    )
    if assignment is None:
        record_access(session, user, action, "review", None, "deny", "reviewer_not_assigned")
        raise HTTPException(status_code=403, detail="reviewer is not assigned to this dataset")
    observe(IDENTITY_REVIEW, labels={"decision": "allow", "reason": "assigned"})
