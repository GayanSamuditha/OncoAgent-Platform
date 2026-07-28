"""Add Temporal execution lineage to CrewAI runs."""

from alembic import op
import sqlalchemy as sa

revision = "0011_temporal_execution"
down_revision = "0010_observability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = [
        sa.Column("temporal_workflow_id", sa.String(200), nullable=True),
        sa.Column("temporal_run_id", sa.String(200), nullable=True),
        sa.Column("temporal_namespace", sa.String(100), nullable=True),
        sa.Column("temporal_task_queue", sa.String(120), nullable=True),
        sa.Column("temporal_execution_status", sa.String(50), nullable=True),
        sa.Column("temporal_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("temporal_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("temporal_last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("temporal_current_stage", sa.String(100), nullable=True),
        sa.Column("temporal_activity_attempt", sa.Integer(), nullable=True),
        sa.Column("temporal_failure_type", sa.String(100), nullable=True),
        sa.Column("temporal_failure_message_redacted", sa.Text(), nullable=True),
        sa.Column("temporal_execution_mode", sa.String(30), nullable=False, server_default="legacy"),
        sa.Column("temporal_correlation_id", sa.String(100), nullable=True),
    ]
    for column in columns:
        op.add_column("crew_runs", column)
    op.create_unique_constraint("uq_crew_runs_temporal_workflow_id", "crew_runs", ["temporal_workflow_id"])
    op.create_index("ix_crew_runs_temporal_run_id", "crew_runs", ["temporal_run_id"])
    op.create_index("ix_crew_runs_temporal_correlation_id", "crew_runs", ["temporal_correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_crew_runs_temporal_correlation_id", table_name="crew_runs")
    op.drop_index("ix_crew_runs_temporal_run_id", table_name="crew_runs")
    op.drop_constraint("uq_crew_runs_temporal_workflow_id", "crew_runs", type_="unique")
    for name in (
        "temporal_correlation_id", "temporal_execution_mode", "temporal_failure_message_redacted",
        "temporal_failure_type", "temporal_activity_attempt", "temporal_current_stage",
        "temporal_last_heartbeat_at", "temporal_completed_at", "temporal_started_at",
        "temporal_execution_status", "temporal_task_queue", "temporal_namespace",
        "temporal_run_id", "temporal_workflow_id",
    ):
        op.drop_column("crew_runs", name)
