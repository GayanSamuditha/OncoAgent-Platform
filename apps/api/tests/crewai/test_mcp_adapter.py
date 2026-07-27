from crewai_client.mcp_client import MCPCall
from crewai_client.tools import tools_for


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def call(self, name: str, arguments: dict[str, object]) -> MCPCall:
        self.calls.append((name, arguments))
        return MCPCall({"items": []}, "request-1", name)


def test_agent_tool_catalog_is_allowlisted_and_protocol_only() -> None:
    client = FakeClient()
    tools = tools_for(client, ["search_clinical_documents"])
    assert [tool.name for tool in tools] == ["search_clinical_documents"]
    tools[0]._run(dataset_id="dataset-1", query="hypertension")
    assert client.calls == [("search_clinical_documents", {"dataset_id": "dataset-1", "query": "hypertension"})]

