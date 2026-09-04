from pathlib import Path

from app.core.config import Settings
from app.core.runtime_config import validate_runtime_settings

ROOT = Path(__file__).resolve().parents[4]


def test_local_defaults_are_valid_for_api() -> None:
    assert validate_runtime_settings(Settings(crewai_enabled=False), service="api") == []


def test_non_local_placeholder_secret_is_rejected() -> None:
    settings = Settings(environment="development")
    fields = {issue.field for issue in validate_runtime_settings(settings)}
    assert "IDENTITY_SIGNING_SECRET" in fields


def test_temporal_worker_requires_explicit_temporal_mode() -> None:
    settings = Settings(crewai_enabled=False, crewai_execution_mode="legacy")
    fields = {issue.field for issue in validate_runtime_settings(settings, service="worker")}
    assert "CREWAI_EXECUTION_MODE" in fields


def test_fault_injection_is_rejected_outside_local() -> None:
    settings = Settings(
        environment="development", crewai_enabled=False, temporal_dev_fault_stage="brief"
    )
    fields = {issue.field for issue in validate_runtime_settings(settings)}
    assert "TEMPORAL_DEV_FAULT_*" in fields


def test_api_requires_nonempty_crewai_mcp_token() -> None:
    settings = Settings(
        crewai_mcp_client_id="crewai-oncology-research",
        crewai_mcp_token="",
        crewai_mcp_dataset_ids="dataset-a",
        crewai_mcp_url="http://mcp:8010/mcp",
    )
    fields = {issue.field for issue in validate_runtime_settings(settings, service="api")}
    assert "CREWAI_MCP_TOKEN" in fields


def test_worker_requires_complete_crewai_mcp_configuration() -> None:
    settings = Settings(
        crewai_mcp_client_id="",
        crewai_mcp_token="",
        crewai_mcp_dataset_ids="",
        crewai_mcp_url="not-a-url",
    )
    fields = {issue.field for issue in validate_runtime_settings(settings, service="worker")}
    assert {
        "CREWAI_MCP_URL",
        "CREWAI_MCP_CLIENT_ID",
        "CREWAI_MCP_TOKEN",
        "CREWAI_MCP_DATASET_IDS",
    }.issubset(fields)


def test_compose_profiles_only_enable_crewai_when_credentials_are_prepared() -> None:
    compose = (ROOT / "infra/docker-compose.yml").read_text(encoding="utf-8")
    local_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    demo_example = (ROOT / ".env.demo.example").read_text(encoding="utf-8")
    demo_preparation = (ROOT / "scripts/prepare_demo_env.py").read_text(encoding="utf-8")

    api_service = compose.split("  api:\n", 1)[1].split("  mcp:\n", 1)[0]
    worker_service = compose.split("  temporal-worker:\n", 1)[1].split(
        "  otel-collector:\n", 1
    )[0]

    assert api_service.count("CREWAI_ENABLED: ${CREWAI_ENABLED:-false}") == 1
    assert worker_service.count("CREWAI_ENABLED: ${CREWAI_ENABLED:-false}") == 1
    assert "CREWAI_ENABLED=false" in local_example
    assert "CREWAI_ENABLED=true" in demo_example
    assert '\"CREWAI_ENABLED\": \"true\"' in demo_preparation
