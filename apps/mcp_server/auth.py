"""Compatibility exports for the shared MCP identity boundary."""

from app.mcp_identity import (
    MCPAuthError,
    MCPClientIdentity,
    authenticate,
    configured_clients,
    headers_from_context,
)

__all__ = ["MCPAuthError", "MCPClientIdentity", "authenticate", "configured_clients", "headers_from_context"]
