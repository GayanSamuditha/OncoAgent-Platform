import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.runtime_config import validate_runtime_settings
from app.observability.metrics import (
    ACTIVE_REQUESTS,
    API_SERVICE,
    HTTP_DURATION,
    HTTP_ERRORS,
    HTTP_REQUESTS,
    initialize_service_metrics,
    observe,
    observe_unsafe_prevention,
    observe_validation_failure,
)
from app.observability.telemetry import configure, current_trace_context
from app.performance.limits import reset_workflow_capacity
from app.services.crewai import recover_incomplete_runs

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    issues = validate_runtime_settings(settings, service="api")
    if issues:
        details = "; ".join(f"{issue.field}: {issue.reason}" for issue in issues)
        raise RuntimeError(f"invalid runtime configuration: {details}")
    # Capacity is intentionally process-local.  Reset it at each application
    # lifespan so a fresh worker never inherits stale in-memory accounting
    # from a previous test/client task or a prior reload.
    reset_workflow_capacity(settings.api_workflow_concurrency)
    configure_logging(settings.log_level)
    initialize_service_metrics(API_SERVICE)
    configure(settings)
    try:
        recovered = recover_incomplete_runs()
        if recovered:
            logger.warning("crewai_runs_marked_interrupted", count=recovered)
    except Exception:
        # Health must remain available even when the optional CrewAI
        # persistence database is unavailable during startup.
        logger.warning("crewai_recovery_unavailable")
    logger.info("api_started", version=settings.app_version, environment=settings.environment)
    yield
    logger.info("api_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if settings.api_docs_enabled else None,
        redoc_url="/redoc" if settings.api_docs_enabled else None,
        openapi_url="/openapi.json" if settings.api_docs_enabled else None,
    )

    @application.options("/{full_path:path}", include_in_schema=False)
    async def cors_preflight(_: str) -> Response:
        """Provide a concrete route for CORS preflight on instrumented apps."""
        return Response(status_code=204)

    if settings.observability_enabled:
        FastAPIInstrumentor.instrument_app(
            application,
            excluded_urls=r"^/health$|^/ready$|^/metrics$",
        )

    @application.middleware("http")
    async def observability_middleware(request: Request, call_next: Any) -> Response:
        content_length = request.headers.get("content-length")
        if (
            content_length
            and content_length.isdigit()
            and int(content_length) > settings.request_max_body_bytes
        ):
            return JSONResponse(
                status_code=413, content={"detail": "request body exceeds configured limit"}
            )
        route = request.url.path
        started = time.perf_counter()
        observe(ACTIVE_REQUESTS, labels={"service": settings.otel_service_name})
        try:
            response = await call_next(request)
            matched_route = request.scope.get("route")
            route_template = getattr(matched_route, "path", None)
            if isinstance(route_template, str) and route_template:
                route = route_template
            trace_id = current_trace_context()["trace_id"]
            status_class = f"{response.status_code // 100}xx"
            observe(
                HTTP_REQUESTS,
                labels={
                    "service": settings.otel_service_name,
                    "route": route,
                    "method": request.method,
                    "status_class": status_class,
                },
            )
            if response.status_code >= 500:
                observe(
                    HTTP_ERRORS,
                    labels={
                        "service": settings.otel_service_name,
                        "route": route,
                        "error_category": "server_error",
                    },
                )
            if response.status_code == 422:
                observe_unsafe_prevention("request_validation")
                observe_validation_failure("request", API_SERVICE)
            response.headers.setdefault("X-Trace-Id", trace_id or "")
            if settings.security_headers_enabled:
                response.headers.setdefault("X-Content-Type-Options", "nosniff")
                response.headers.setdefault("X-Frame-Options", "DENY")
                response.headers.setdefault("Referrer-Policy", "no-referrer")
                response.headers.setdefault(
                    "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
                )
                response.headers.setdefault(
                    "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
                )
                if settings.security_hsts_enabled:
                    response.headers.setdefault(
                        "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
                    )
            return cast(Response, response)
        except Exception:
            observe(
                HTTP_ERRORS,
                labels={
                    "service": settings.otel_service_name,
                    "route": route,
                    "error_category": "unhandled",
                },
            )
            raise
        finally:
            matched_route = request.scope.get("route")
            route_template = getattr(matched_route, "path", None)
            if isinstance(route_template, str) and route_template:
                route = route_template
            observe(
                HTTP_DURATION,
                (time.perf_counter() - started),
                {"service": settings.otel_service_name, "route": route, "method": request.method},
            )
            observe(ACTIVE_REQUESTS, -1, {"service": settings.otel_service_name})

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Authorization",
            "Content-Type",
            "Origin",
            "X-Idempotency-Key",
            "X-Trace-Id",
        ],
    )
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
    application.include_router(router)
    return application


app = create_app()
