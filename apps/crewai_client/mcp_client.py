"""Official MCP SDK client used by CrewAI BaseTool adapters."""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


@dataclass(frozen=True)
class MCPCall:
    result: dict[str, Any]
    request_id: str
    tool_name: str


class MCPClientProtocol(Protocol):
    def call(self, tool_name: str, arguments: dict[str, Any]) -> MCPCall: ...


class MCPGatewayClient:
    def __init__(
        self, url: str, client_id: str, token: str, max_calls: int = 30, run_id: str | None = None
    ) -> None:
        self.url, self.client_id, self.token = url, client_id, token
        self.max_calls, self.calls = max_calls, 0
        self.run_id = run_id
        self.request_ids: list[str] = []
        self.request_context: list[dict[str, str]] = []

    async def _call_async(self, tool_name: str, arguments: dict[str, Any]) -> MCPCall:
        import httpx

        headers = {
            "x-mcp-client-id": self.client_id,
            "authorization": f"Bearer {self.token}",
            "x-correlation-id": str(uuid.uuid4()),
        }
        async with httpx.AsyncClient(headers=headers, timeout=30) as http_client:
            async with streamable_http_client(self.url, http_client=http_client) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        tool_name,
                        {"request": arguments},
                        read_timeout_seconds=timedelta(seconds=30),
                    )
                    data: dict[str, Any] = dict(result.structuredContent or {})
                    if result.isError:
                        raise RuntimeError("MCP tool returned a safe error")
                    request_id = str(data.get("correlation_id", uuid.uuid4()))
                    self.request_ids.append(request_id)
                    task_name, agent_role = {
                        "search_clinical_documents": ("candidate_discovery", "Cohort Researcher"),
                        "build_patient_evidence": ("eligibility_evidence_review", "Eligibility Evidence Reviewer"),
                    }.get(
                        tool_name,
                        ("structured_evidence_collection", "Structured Evidence Investigator"),
                    )
                    self.request_context.append(
                        {
                            "request_id": request_id,
                            "run_id": self.run_id or "",
                            "tool_name": tool_name,
                            "task_name": task_name,
                            "agent_role": agent_role,
                        }
                    )
                    return MCPCall(result=data, request_id=request_id, tool_name=tool_name)

    def call(self, tool_name: str, arguments: dict[str, Any]) -> MCPCall:
        if self.calls >= self.max_calls:
            raise RuntimeError("maximum MCP tool calls exceeded")
        self.calls += 1
        return asyncio.run(self._call_async(tool_name, arguments))
