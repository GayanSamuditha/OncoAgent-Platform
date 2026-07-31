import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from apps.mcp_server.gateway import MCPGateway  # type: ignore[import-not-found]

from app.core.config import Settings
from app.mcp_identity import MCPAuthError, authenticate

CLIENTS = '[{"client_id":"client-a","token":"token-a","actor_id":"actor-a","actor_role":"researcher","client_type":"test","dataset_ids":["dataset-a"]}]'


def gateway() -> MCPGateway:
    return MCPGateway(Settings(mcp_dev_clients=CLIENTS))


def test_official_sdk_discovers_exact_read_only_catalog() -> None:
    tools = asyncio.run(gateway().server.list_tools())
    names = {item.name for item in tools}
    assert names == {
        "search_clinical_documents",
        "get_patient_demographics",
        "get_patient_conditions",
        "get_patient_observations",
        "get_patient_procedures",
        "get_patient_medications",
        "get_patient_diagnostic_reports",
        "get_patient_encounters",
        "verify_date_window",
        "build_patient_evidence",
    }
    assert all(gateway().registry[name].descriptor.read_only for name in names)


def test_missing_credentials_are_rejected_without_database_access() -> None:
    result = gateway().execute(
        "get_patient_demographics", {"dataset_id": "dataset-a", "patient_id": "p"}
    )
    assert result["error"]["category"] == "unknown_client"


def test_unknown_tool_and_unknown_fields_are_rejected() -> None:
    g = gateway()
    g._audit = lambda *args, **kwargs: None  # type: ignore[method-assign]
    unknown = g.execute("arbitrary_sql", {}, stdio=True)
    assert unknown["error"]["category"] == "unknown_client"
    import os

    os.environ["MCP_STDIO_CLIENT_ID"] = "client-a"
    os.environ["MCP_STDIO_TOKEN"] = "token-a"
    try:
        unknown = g.execute("arbitrary_sql", {}, stdio=True)
        invalid = g.execute(
            "get_patient_demographics",
            {"dataset_id": "dataset-a", "patient_id": "p", "extra": True},
            stdio=True,
        )
    finally:
        os.environ.pop("MCP_STDIO_CLIENT_ID", None)
        os.environ.pop("MCP_STDIO_TOKEN", None)
    assert unknown["error"]["category"] == "unknown_tool"
    assert invalid["error"]["category"] == "invalid_arguments"


def test_mcp_kill_switch_denies_execution() -> None:
    settings = Settings(mcp_enabled=False, mcp_dev_clients=CLIENTS)
    result = MCPGateway(settings).execute(
        "get_patient_demographics", {"dataset_id": "dataset-a", "patient_id": "p"}, stdio=True
    )
    assert result["error"]["category"] == "authorization_denied"


def test_configured_client_authenticates() -> None:
    identity = authenticate(
        Settings(mcp_dev_clients=CLIENTS),
        {"x-mcp-client-id": "client-a", "authorization": "Bearer token-a"},
    )
    assert identity.client_id == "client-a"
    assert identity.dataset_ids == frozenset({"dataset-a"})


def test_mismatched_token_is_denied() -> None:
    try:
        authenticate(
            Settings(mcp_dev_clients=CLIENTS),
            {"x-mcp-client-id": "client-a", "authorization": "Bearer wrong-token"},
        )
    except MCPAuthError as exc:
        assert exc.category == "authentication_failed"
    else:
        raise AssertionError("mismatched MCP token was accepted")


def test_missing_mcp_client_is_denied() -> None:
    try:
        authenticate(
            Settings(mcp_dev_clients=CLIENTS),
            {"x-mcp-client-id": "missing", "authorization": "Bearer token-a"},
        )
    except MCPAuthError as exc:
        assert exc.category == "unknown_client"
    else:
        raise AssertionError("unregistered MCP client was accepted")


def test_unauthorized_dataset_is_denied_before_database_access() -> None:
    identity = authenticate(
        Settings(mcp_dev_clients=CLIENTS),
        {"x-mcp-client-id": "client-a", "authorization": "Bearer token-a"},
    )
    try:
        gateway()._dataset(identity, "dataset-b")
    except MCPAuthError as exc:
        assert exc.category == "dataset_not_allowed"
    else:
        raise AssertionError("unauthorized dataset was accepted")
