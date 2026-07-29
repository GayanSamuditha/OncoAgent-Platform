"""Startup configuration checks shared by local service entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from app.core.config import Settings


@dataclass(frozen=True)
class ConfigIssue:
    field: str
    reason: str


def validate_runtime_settings(settings: Settings, *, service: str = "api") -> list[ConfigIssue]:
    """Return safe diagnostics without exposing values or secrets."""

    issues: list[ConfigIssue] = []
    database = urlparse(settings.database_url)
    if database.scheme not in {"postgresql", "postgresql+psycopg"} or not database.hostname:
        issues.append(ConfigIssue("DATABASE_URL", "must be a PostgreSQL URL with a hostname"))
    if settings.environment not in {"local", "test"}:
        if settings.identity_signing_secret == "local-development-only-change-me":
            issues.append(
                ConfigIssue(
                    "IDENTITY_SIGNING_SECRET", "placeholder is not allowed outside local/test"
                )
            )
        if settings.identity_legacy_headers_enabled:
            issues.append(
                ConfigIssue("IDENTITY_LEGACY_HEADERS_ENABLED", "must be false outside local/test")
            )
        if settings.temporal_dev_fault_stage or settings.temporal_dev_fault_category:
            issues.append(ConfigIssue("TEMPORAL_DEV_FAULT_*", "fault injection is local/test only"))
        if not settings.identity_cookie_secure:
            issues.append(ConfigIssue("IDENTITY_COOKIE_SECURE", "must be true outside local/test"))
        if settings.security_hsts_enabled is False:
            issues.append(ConfigIssue("SECURITY_HSTS_ENABLED", "must be true outside local/test"))
    if settings.temporal_enabled:
        if not settings.temporal_address:
            issues.append(ConfigIssue("TEMPORAL_ADDRESS", "is required when Temporal is enabled"))
        if not settings.temporal_namespace or not settings.temporal_task_queue:
            issues.append(
                ConfigIssue(
                    "TEMPORAL_NAMESPACE/TASK_QUEUE", "are required when Temporal is enabled"
                )
            )
        if service == "worker" and settings.crewai_execution_mode != "temporal":
            issues.append(
                ConfigIssue("CREWAI_EXECUTION_MODE", "worker requires explicit temporal mode")
            )
    if service == "worker":
        if not settings.crewai_mcp_url or not settings.crewai_mcp_client_id:
            issues.append(ConfigIssue("CREWAI_MCP_URL/CLIENT_ID", "are required for the worker"))
        if not settings.crewai_mcp_dataset_ids:
            issues.append(ConfigIssue("CREWAI_MCP_DATASET_IDS", "requires an allowlisted dataset"))
    if settings.mcp_enabled and not settings.mcp_host:
        issues.append(ConfigIssue("MCP_HOST", "is required when MCP is enabled"))
    issuer = urlparse(settings.identity_issuer)
    if settings.identity_enabled and (issuer.scheme not in {"http", "https"} or not issuer.netloc):
        issues.append(ConfigIssue("IDENTITY_ISSUER", "must be an absolute HTTP(S) issuer URL"))
    if settings.identity_enabled and not settings.identity_audience:
        issues.append(ConfigIssue("IDENTITY_AUDIENCE", "is required when identity is enabled"))
    if not settings.retrieval_profile:
        issues.append(ConfigIssue("RETRIEVAL_PROFILE", "must not be empty"))
    if service == "worker":
        model_endpoint = urlparse(settings.crewai_ollama_base_url)
        if model_endpoint.scheme not in {"http", "https"} or not model_endpoint.netloc:
            issues.append(ConfigIssue("CREWAI_OLLAMA_BASE_URL", "must be an absolute HTTP(S) URL"))
        if not settings.crewai_default_model:
            issues.append(ConfigIssue("CREWAI_DEFAULT_MODEL", "is required for the worker"))
    if settings.observability_enabled and not settings.otel_exporter_otlp_endpoint:
        issues.append(
            ConfigIssue("OTEL_EXPORTER_OTLP_ENDPOINT", "is required when observability is enabled")
        )
    return issues
