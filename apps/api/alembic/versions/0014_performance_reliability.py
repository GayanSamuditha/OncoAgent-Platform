"""Add bounded performance and reliability records."""

import sqlalchemy as sa
from alembic import op

revision = "0014_performance_reliability"
down_revision = "0013_release_evaluation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "performance_test_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plan_id", sa.String(120), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("profile_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("manifest", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("plan_id", "version", name="uq_performance_plan_version"),
    )
    op.create_table(
        "performance_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("execution_id", sa.String(120), nullable=False),
        sa.Column("plan_id", sa.String(120), nullable=False),
        sa.Column("profile_id", sa.String(120), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.id"), nullable=True),
        sa.Column("manifest", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("report_reference", sa.String(500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("execution_id", name="uq_performance_execution_id"),
    )
    op.create_table(
        "performance_metrics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("execution_id", sa.String(120), nullable=False),
        sa.Column("name", sa.String(160), nullable=False), sa.Column("value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(40), nullable=False), sa.Column("status", sa.String(30), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"), sa.Column("denominator", sa.Integer(), nullable=True),
        sa.Column("definition", sa.Text(), nullable=False),
    )
    op.create_index("ix_performance_metrics_execution_id", "performance_metrics", ["execution_id"])
    op.create_table(
        "performance_slos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("execution_id", sa.String(120), nullable=False),
        sa.Column("name", sa.String(160), nullable=False), sa.Column("value", sa.Float(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True), sa.Column("status", sa.String(30), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text(), nullable=False),
    )
    op.create_index("ix_performance_slos_execution_id", "performance_slos", ["execution_id"])
    op.create_table(
        "performance_findings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("execution_id", sa.String(120), nullable=False),
        sa.Column("category", sa.String(100), nullable=False), sa.Column("severity", sa.String(30), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False), sa.Column("limitation", sa.Text(), nullable=False),
    )
    op.create_index("ix_performance_findings_execution_id", "performance_findings", ["execution_id"])


def downgrade() -> None:
    for table in ("performance_findings", "performance_slos", "performance_metrics", "performance_executions", "performance_test_plans"):
        op.drop_table(table)
