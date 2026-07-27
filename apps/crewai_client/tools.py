"""CrewAI tools are thin protocol adapters, never domain implementations."""

from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from .mcp_client import MCPClientProtocol

try:
    from crewai.tools import BaseTool
except Exception:  # pragma: no cover

    class BaseTool:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str
    patient_id: str | None = None
    query: str | None = None
    top_k: int | None = None
    retrieval_profile: str | None = None
    timestamp: str | None = None
    date_window: dict[str, str] | None = None


class MCPPlatformTool(BaseTool):
    tool_name: str
    client: Any

    def __init__(self, tool_name: str, client: MCPClientProtocol) -> None:
        base_init = cast(Any, super().__init__)
        base_init(
            name=tool_name,
            description=f"Read-only synthetic data tool {tool_name}; all calls go through MCP.",
            args_schema=ToolArguments,
            tool_name=tool_name,
            client=client,
        )

    def _run(self, **kwargs: Any) -> str:
        allowed = {key: value for key, value in kwargs.items() if value is not None}
        return str(self.client.call(self.tool_name, allowed).result)


def tools_for(client: MCPClientProtocol, names: list[str]) -> list[MCPPlatformTool]:
    return [MCPPlatformTool(name, client) for name in names]
