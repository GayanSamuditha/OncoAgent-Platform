import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from apps.mcp_server.gateway import MCPGateway  # type: ignore[import-not-found]

from app.core.config import Settings

CLIENTS = '[{"client_id":"client-a","token":"token-a","actor_id":"actor-a","actor_role":"researcher","client_type":"test","dataset_ids":["dataset-a"]}]'


def gateway() -> MCPGateway:
    return MCPGateway(Settings(mcp_dev_clients=CLIENTS))


def test_official_sdk_discovers_exact_read_only_catalog() -> None:
    tools = asyncio.run(gateway().server.list_tools())
    names = {item.name for item in tools}
    assert names == {"search_clinical_documents", "get_patient_demographics", "get_patient_conditions", "get_patient_observations", "get_patient_procedures", "get_patient_medications", "get_patient_diagnostic_reports", "get_patient_encounters", "verify_date_window", "build_patient_evidence"}


def test_missing_credentials_are_rejected_without_database_access() -> None:
    result = gateway().execute("get_patient_demographics", {"dataset_id": "dataset-a", "patient_id": "p"})
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
        invalid = g.execute("get_patient_demographics", {"dataset_id": "dataset-a", "patient_id": "p", "extra": True}, stdio=True)
    finally:
        os.environ.pop("MCP_STDIO_CLIENT_ID", None)
        os.environ.pop("MCP_STDIO_TOKEN", None)
    assert unknown["error"]["category"] == "unknown_tool"
    assert invalid["error"]["category"] == "invalid_arguments"


def test_mcp_kill_switch_denies_execution() -> None:
    settings = Settings(mcp_enabled=False, mcp_dev_clients=CLIENTS)
    result = MCPGateway(settings).execute("get_patient_demographics", {"dataset_id": "dataset-a", "patient_id": "p"}, stdio=True)
    assert result["error"]["category"] == "authorization_denied"
