import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.observability.metrics import (
    ACTIVE_REQUESTS,
    HTTP_DURATION,
    HTTP_ERRORS,
    HTTP_REQUESTS,
    observe,
)
from app.observability.telemetry import configure, current_trace_context
from app.services.crewai import recover_incomplete_runs

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
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
    application = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    if settings.observability_enabled:
        FastAPIInstrumentor.instrument_app(
            application,
            excluded_urls=r"^/health$|^/ready$|^/metrics$",
        )

    @application.middleware("http")
    async def observability_middleware(request: Request, call_next: Any) -> Response:
        route = request.url.path if request.url.path in {"/health", "/ready", "/metrics"} else request.url.path
        started = time.perf_counter()
        observe(ACTIVE_REQUESTS, labels={"service": settings.otel_service_name})
        try:
            response = await call_next(request)
            trace_id = current_trace_context()["trace_id"]
            status_class = f"{response.status_code // 100}xx"
            observe(HTTP_REQUESTS, labels={"service": settings.otel_service_name, "route": route, "method": request.method, "status_class": status_class})
            if response.status_code >= 500:
                observe(HTTP_ERRORS, labels={"service": settings.otel_service_name, "route": route, "error_category": "server_error"})
            response.headers.setdefault("X-Trace-Id", trace_id or "")
            return cast(Response, response)
        except Exception:
            observe(HTTP_ERRORS, labels={"service": settings.otel_service_name, "route": route, "error_category": "unhandled"})
            raise
        finally:
            observe(HTTP_DURATION, (time.perf_counter() - started), {"service": settings.otel_service_name, "route": route, "method": request.method})
            observe(ACTIVE_REQUESTS, -1, {"service": settings.otel_service_name})
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    application.include_router(router)
    return application


app = create_app()
