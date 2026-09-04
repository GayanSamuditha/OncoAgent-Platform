"""Tamper-evident verification for access-decision audit records."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.identity import AccessDecisionAudit
from app.security.contracts import AuditIntegrityResult

INTEGRITY_VERSION = "sha256-chain-v1"
# PostgreSQL advisory locks are shared across application processes.  A fixed,
# application-specific key serializes audit-chain tip reads and appends without
# locking unrelated tables for the duration of the request transaction.
AUDIT_CHAIN_LOCK_ID = 1_329_743_087


def canonical_payload(item: AccessDecisionAudit) -> dict[str, Any]:
    return {
        "id": item.id,
        "actor_id": item.actor_id,
        "action": item.action,
        "resource_type": item.resource_type,
        "resource_id": item.resource_id,
        "decision": item.decision,
        "reason_code": item.reason_code,
        "correlation_id": item.correlation_id,
        "trace_id": item.trace_id,
        "details": item.details or {},
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "previous_digest": item.previous_digest,
    }


def digest_for(item: AccessDecisionAudit) -> str:
    return hashlib.sha256(
        json.dumps(canonical_payload(item), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def acquire_audit_chain_lock(session: Session) -> None:
    """Serialize chain appends on PostgreSQL for the current transaction."""
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": AUDIT_CHAIN_LOCK_ID},
        )


def append_audit_record(session: Session, item: AccessDecisionAudit) -> None:
    """Append one record after the current chain tip without creating forks."""
    acquire_audit_chain_lock(session)
    previous = session.scalar(
        select(AccessDecisionAudit)
        .where(AccessDecisionAudit.canonical_digest.is_not(None))
        .order_by(AccessDecisionAudit.created_at.desc(), AccessDecisionAudit.id.desc())
    )
    # PostgreSQL's ``now()`` is the transaction start time.  Leaving created_at
    # to that server default can therefore sort two serialized appends in the
    # opposite order when one transaction waited for the advisory lock.  Stamp
    # the record while holding the lock and keep the timestamp monotonic so the
    # timestamp-ordered verifier and the selected chain tip agree.
    created_at = datetime.now(UTC)
    if previous is not None and previous.created_at is not None:
        previous_created_at = previous.created_at
        if previous_created_at.tzinfo is None:
            previous_created_at = previous_created_at.replace(tzinfo=UTC)
        if created_at <= previous_created_at:
            created_at = previous_created_at + timedelta(microseconds=1)
    item.created_at = created_at
    item.previous_digest = previous.canonical_digest if previous else None
    item.integrity_version = INTEGRITY_VERSION
    session.add(item)
    session.flush()
    item.canonical_digest = digest_for(item)


def verify_audit_chain(session: Session) -> AuditIntegrityResult:
    items = session.scalars(
        select(AccessDecisionAudit).order_by(
            AccessDecisionAudit.created_at.asc(), AccessDecisionAudit.id.asc()
        )
    ).all()
    legacy = [item.id for item in items if not item.canonical_digest or not item.integrity_version]
    changed: list[str] = []
    previous: str | None = None
    for item in items:
        if not item.canonical_digest or not item.integrity_version:
            continue
        if item.previous_digest != previous or digest_for(item) != item.canonical_digest:
            changed.append(item.id)
        previous = item.canonical_digest
    return AuditIntegrityResult(
        status="failed" if changed else "legacy_unverified" if legacy else "verified",
        checked_records=len(items),
        legacy_records=len(legacy),
        changed_records=changed,
        limitations=[
            "Historical records without integrity fields remain "
            "legacy_unverified and were not rewritten."
        ]
        if legacy
        else [],
    )
