"""Add MCP gateway audit records."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_mcp_gateway"
down_revision = "0006_local_qwen_planner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("protocol_version", sa.String(length=40), nullable=False),
        sa.Column("server_version", sa.String(length=40), nullable=False),
        sa.Column("client_id", sa.String(length=120), nullable=False),
        sa.Column("actor_id", sa.String(length=200), nullable=False),
        sa.Column("actor_role", sa.String(length=40), nullable=False),
        sa.Column("client_type", sa.String(length=40), nullable=False),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("tool_version", sa.String(length=40), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=True),
        sa.Column("sanitized_arguments", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("response_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("error_category", sa.String(length=60), nullable=True),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column("retrieval_lineage", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("client_id", "actor_id", "correlation_id", "tool_name", "dataset_id", "status"):
        op.create_index(f"ix_mcp_requests_{column}", "mcp_requests", [column])


def downgrade() -> None:
    op.drop_table("mcp_requests")
