from fastapi.testclient import TestClient

from app.api.routes import get_db
from app.main import app


def test_health_does_not_require_database(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_platform_info_declares_phase_zero_capabilities(client: TestClient) -> None:
    response = client.get("/api/v1/platform/info")
    body = response.json()
    assert response.status_code == 200
    assert body["data_policy"] == "Synthetic Synthea data only."
    assert body["clinical_validation_status"] == "Not clinically validated."
    assert "Platform health and readiness reporting" in body["capabilities"]["implemented"]
    assert (
        "Governed LangGraph cohort workflow with human approval"
        in body["capabilities"]["implemented"]
    )


def test_ready_reports_database_failure(client: TestClient) -> None:
    class BrokenSession:
        def execute(self, _query):
            raise RuntimeError("database unavailable")

    def failing_db():
        yield BrokenSession()

    app.dependency_overrides[get_db] = failing_db
    try:
        response = client.get("/ready")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
