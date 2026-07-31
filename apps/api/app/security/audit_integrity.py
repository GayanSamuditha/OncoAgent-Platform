"""Tamper-evident verification for access-decision audit records."""

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import AccessDecisionAudit
from app.security.contracts import AuditIntegrityResult

INTEGRITY_VERSION = "sha256-chain-v1"


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
