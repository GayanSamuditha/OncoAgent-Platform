"""Persist normalized MCP request-to-task context for governance audits."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009_prov_audit"
down_revision = "0008_crewai_crew"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crew_lineage",
        sa.Column(
            "mcp_request_context",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("crew_lineage", "mcp_request_context")
