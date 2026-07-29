from types import SimpleNamespace

from app.security.audit_integrity import digest_for


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
