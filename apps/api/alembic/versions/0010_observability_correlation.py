"""Add safe trace correlation identifiers to application audit records."""

import sqlalchemy as sa
from alembic import op

revision = "0010_observability"
down_revision = "0009_prov_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("workflow_runs", "workflow_events", "crew_runs", "crew_tasks", "crew_events", "mcp_requests"):
        op.add_column(table, sa.Column("trace_id", sa.String(length=32), nullable=True))
        op.add_column(table, sa.Column("span_id", sa.String(length=16), nullable=True))
        op.create_index(f"ix_{table}_trace_id", table, ["trace_id"])


def downgrade() -> None:
    for table in ("workflow_runs", "workflow_events", "crew_runs", "crew_tasks", "crew_events", "mcp_requests"):
        op.drop_index(f"ix_{table}_trace_id", table_name=table)
        op.drop_column(table, "span_id")
        op.drop_column(table, "trace_id")
