from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_local_login_sets_session_and_returns_server_side_role() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/auth/login", json={"user_key": "researcher-console"})
        assert response.status_code == 200
        assert response.json()["role"] == "researcher"
        assert "oncoagent_session" in response.cookies
        current = client.get("/api/v1/auth/me")
        assert current.status_code == 200
        assert current.json()["subject"] == "researcher-console"


def test_missing_authentication_is_rejected_for_protected_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/temporal/status")
        assert response.status_code == 401


def test_invalid_issuer_and_expired_tokens_are_rejected() -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    for claims in (
        {"iss": "https://wrong.example", "aud": settings.identity_audience, "sub": "researcher-console", "exp": now + timedelta(minutes=5)},
        {"iss": settings.identity_issuer, "aud": settings.identity_audience, "sub": "researcher-console", "exp": now - timedelta(minutes=5)},
    ):
        token = jwt.encode(claims, settings.identity_signing_secret, algorithm="HS256")
        with TestClient(app) as client:
            response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 401


def test_cookie_state_change_requires_configured_origin() -> None:
    with TestClient(app) as client:
        assert client.post("/api/v1/auth/login", json={"user_key": "researcher-console"}).status_code == 200
        denied = client.post("/api/v1/auth/logout", headers={"Origin": "https://untrusted.example"})
        assert denied.status_code == 403
        allowed = client.post("/api/v1/auth/logout", headers={"Origin": "http://localhost:3000"})
        assert allowed.status_code == 200


def test_crew_request_cannot_replace_authenticated_actor_context() -> None:
    with TestClient(app) as client:
        assert client.post("/api/v1/auth/login", json={"user_key": "researcher-console"}).status_code == 200
        response = client.post(
            "/api/v1/crews/oncology-research/runs",
            headers={"Origin": "http://localhost:3000"},
            json={
                "dataset_id": "6b15ce38-e12c-4482-866e-59d333952024",
                "research_question": "Find synthetic adults with hypertension",
                "structured_criteria": [{"criterion_type": "condition", "clinical_concept": "hypertension"}],
                "maximum_candidates": 1,
                "retrieval_profile": "postgres_fts",
                "model_profile": "automatic",
                "actor_context": {"actor_id": "admin-console", "actor_role": "admin"},
            },
        )
        assert response.status_code == 403
