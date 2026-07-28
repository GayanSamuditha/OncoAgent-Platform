"""Application audit records for the separate MCP gateway."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MCPRequest(Base):
    __tablename__ = "mcp_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    protocol_version: Mapped[str] = mapped_column(String(40))
    server_version: Mapped[str] = mapped_column(String(40))
    client_id: Mapped[str] = mapped_column(String(120), index=True)
    actor_id: Mapped[str] = mapped_column(String(200), index=True)
    actor_role: Mapped[str] = mapped_column(String(40))
    client_type: Mapped[str] = mapped_column(String(40))
    correlation_id: Mapped[str] = mapped_column(String(36), index=True)
    tool_name: Mapped[str] = mapped_column(String(100), index=True)
    tool_version: Mapped[str] = mapped_column(String(40))
    dataset_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    sanitized_arguments: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(30), index=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    response_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float | None] = mapped_column(nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieval_lineage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    span_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
