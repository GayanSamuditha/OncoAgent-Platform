from app.core.config import Settings
from app.core.runtime_config import validate_runtime_settings


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
