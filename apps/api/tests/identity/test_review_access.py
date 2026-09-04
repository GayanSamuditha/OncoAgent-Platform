from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import routes
from app.identity.service import AuthenticatedUser
from app.observability.metrics import SECURITY_SELF_APPROVAL_DENIALS


class SessionContext:
    def add(self, _value):
        return None

    def commit(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def reviewer() -> AuthenticatedUser:
    return AuthenticatedUser(
        internal_id="reviewer-internal",
        subject="reviewer-console",
        issuer="local",
        display_name="Reviewer",
        email=None,
        role="reviewer",
        permissions=frozenset({"workflow:read-own", "review:read-assigned", "review:decide", "dataset:use"}),
        dataset_ids=frozenset({"dataset-a"}),
    )


def test_assigned_reviewer_path_does_not_apply_run_ownership(monkeypatch) -> None:
    run = SimpleNamespace(dataset_id="dataset-a", actor_id="researcher-console")
    monkeypatch.setattr(routes, "_crew_get", lambda _run_id: run)
    monkeypatch.setattr(routes, "SessionLocal", lambda: SessionContext())
    monkeypatch.setattr(routes, "require_dataset", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(routes, "require_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(routes, "require_reviewer", lambda *_args, **_kwargs: None)
    assert routes._review_authorized_crew_get("run-a", reviewer()).dataset_id == "dataset-a"


def test_creator_cannot_decide_through_review_path(monkeypatch) -> None:
    run = SimpleNamespace(dataset_id="dataset-a", actor_id="researcher-console")
    creator = reviewer().__class__(**{**reviewer().__dict__, "subject": "researcher-console", "role": "researcher"})
    monkeypatch.setattr(routes, "_crew_get", lambda _run_id: run)
    monkeypatch.setattr(routes, "SessionLocal", lambda: SessionContext())
    monkeypatch.setattr(routes, "require_dataset", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(routes, "require_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(routes, "record_access", lambda *_args, **_kwargs: None)
    before = SECURITY_SELF_APPROVAL_DENIALS._value.get()
    with pytest.raises(HTTPException) as exc:
        routes._review_authorized_crew_get("run-a", creator, deciding=True)
    assert exc.value.status_code == 403
    assert SECURITY_SELF_APPROVAL_DENIALS._value.get() == before + 1
