"""Shared development-only identity parsing for the MCP gateway and API."""

import json
import os
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings


@dataclass(frozen=True)
class MCPClientIdentity:
    client_id: str
    token: str
    actor_id: str
    actor_role: str
    client_type: str
    dataset_ids: frozenset[str]


class MCPAuthError(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


def configured_clients(settings: Settings) -> dict[str, MCPClientIdentity]:
    raw = settings.mcp_dev_clients or os.getenv("MCP_DEV_CLIENTS", "")
    if not raw:
        return {}
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MCPAuthError("internal_safe_failure", "MCP client configuration is invalid") from exc
    if not isinstance(entries, list):
        raise MCPAuthError("internal_safe_failure", "MCP client configuration is invalid")
    result: dict[str, MCPClientIdentity] = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        client_id = item.get("client_id")
        token = item.get("token")
        actor_id = item.get("actor_id")
        actor_role = item.get("actor_role")
        client_type = item.get("client_type", "service")
        datasets = item.get("dataset_ids", [])
        if (
            not all(
                isinstance(value, str) and value
                for value in (client_id, token, actor_id, actor_role)
            )
            or not isinstance(client_type, str)
            or not isinstance(datasets, list)
        ):
            continue
        if actor_role not in {"researcher", "reviewer", "admin", "service"}:
            continue
        assert isinstance(client_id, str)
        assert isinstance(token, str)
        assert isinstance(actor_id, str)
        assert isinstance(actor_role, str)
        result[client_id] = MCPClientIdentity(
            client_id, token, actor_id, actor_role, client_type,
            frozenset(str(value) for value in datasets),
        )
    return result


def authenticate(
    settings: Settings, headers: dict[str, str], stdio: bool = False
) -> MCPClientIdentity:
    client_id = headers.get("x-mcp-client-id") or (
        os.getenv("MCP_STDIO_CLIENT_ID") if stdio else None
    )
    token = headers.get("authorization", "")
    if token.lower().startswith("bearer "):
        token = token[7:]
    token = token or (os.getenv("MCP_STDIO_TOKEN", "") if stdio else "")
    client = configured_clients(settings).get(client_id or "")
    if client is None:
        raise MCPAuthError("unknown_client", "MCP client is not registered")
    if not token or token != client.token:
        raise MCPAuthError("authentication_failed", "MCP credentials were not accepted")
    return client


def headers_from_context(context: Any) -> dict[str, str]:
    request = getattr(getattr(context, "request_context", None), "request", None)
    headers = getattr(request, "headers", {})
    return {str(key).lower(): str(value) for key, value in headers.items()}
