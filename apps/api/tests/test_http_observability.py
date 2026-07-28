from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.main import app


def test_observability_health_endpoints_complete_without_context_errors() -> None:
    with TestClient(app, raise_server_exceptions=True) as client:
        for path in ("/health", "/ready", "/metrics", "/api/v1/observability/status"):
            response = client.get(path)
            assert response.status_code in {200, 503}


def test_fastapi_has_one_inbound_otel_owner() -> None:
    with TestClient(app):
        owners = []
        middleware = app.middleware_stack
        while middleware is not None:
            if type(middleware).__name__ == "OpenTelemetryMiddleware":
                owners.append(middleware)
            middleware = getattr(middleware, "app", None)
    assert len(owners) == 1


def test_concurrent_requests_complete_with_isolated_request_contexts() -> None:
    def request_health(_: int) -> tuple[int, str]:
        with TestClient(app, raise_server_exceptions=True) as client:
            response = client.get("/health")
            return response.status_code, response.headers.get("x-trace-id", "")

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(request_health, range(20)))
    assert all(status == 200 for status, _ in results)
    trace_ids = [trace_id for _, trace_id in results if trace_id]
    assert len(trace_ids) in {0, 20}
    if trace_ids:
        assert len(set(trace_ids)) == len(trace_ids)
