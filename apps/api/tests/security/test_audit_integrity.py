from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

from sqlalchemy.orm import Session

from app.models.identity import AccessDecisionAudit
from app.security.audit_integrity import (
    INTEGRITY_VERSION,
    append_audit_record,
    digest_for,
)


def test_audit_digest_is_deterministic_and_does_not_require_raw_payloads() -> None:
    item = SimpleNamespace(
        id="audit-1",
        actor_id="user-1",
        action="read",
        resource_type="run",
        resource_id="run-1",
        decision="allow",
        reason_code="granted",
        correlation_id="corr-1",
        trace_id="trace-1",
        details={},
        created_at=None,
        previous_digest=None,
    )
    first = digest_for(item)
    assert first == digest_for(item)
    assert len(first) == 64


class RecordingSession:
    def __init__(self, dialect: str, previous: Any = None) -> None:
        self.dialect = SimpleNamespace(name=dialect)
        self.previous = previous
        self.events: list[str] = []

    def get_bind(self) -> SimpleNamespace:
        return SimpleNamespace(dialect=self.dialect)

    def execute(self, *_: Any, **__: Any) -> None:
        self.events.append("lock")

    def scalar(self, *_: Any, **__: Any) -> Any:
        self.events.append("tip")
        return self.previous

    def add(self, _: Any) -> None:
        self.events.append("add")

    def flush(self) -> None:
        self.events.append("flush")


def test_append_audit_record_locks_before_reading_postgres_chain_tip() -> None:
    previous = SimpleNamespace(
        canonical_digest="a" * 64,
        created_at=datetime(2099, 1, 1, tzinfo=UTC),
    )
    session = RecordingSession("postgresql", previous)
    item = AccessDecisionAudit(
        id="audit-2",
        actor_id=None,
        action="read",
        resource_type="run",
        resource_id="run-2",
        decision="allow",
        reason_code="granted",
        correlation_id=None,
        trace_id=None,
        details={},
    )

    append_audit_record(cast(Session, session), item)

    assert session.events == ["lock", "tip", "add", "flush"]
    assert item.previous_digest == previous.canonical_digest
    assert item.created_at > previous.created_at
    assert item.integrity_version == INTEGRITY_VERSION
    assert item.canonical_digest == digest_for(item)


def test_append_audit_record_does_not_use_postgres_lock_on_sqlite() -> None:
    session = RecordingSession("sqlite")
    item = AccessDecisionAudit(
        id="audit-3",
        actor_id=None,
        action="read",
        resource_type="run",
        resource_id="run-3",
        decision="allow",
        reason_code="granted",
        correlation_id=None,
        trace_id=None,
        details={},
    )

    append_audit_record(cast(Session, session), item)

    assert session.events == ["tip", "add", "flush"]
    assert item.previous_digest is None
    assert item.canonical_digest == digest_for(item)
