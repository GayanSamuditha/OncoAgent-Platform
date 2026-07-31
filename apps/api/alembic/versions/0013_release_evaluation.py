"""Add versioned release-candidate evaluation records."""

import sqlalchemy as sa
from alembic import op

revision = "0013_release_evaluation"
down_revision = "0012_identity_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "release_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("candidate_id", sa.String(120), nullable=False, index=True),
        sa.Column("candidate_version", sa.String(80), nullable=False),
        sa.Column("baseline_id", sa.String(120), nullable=True),
        sa.Column("baseline_version", sa.String(80), nullable=True),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.id"), nullable=False, index=True),
        sa.Column("evaluation_suite_version", sa.String(80), nullable=False),
        sa.Column("artifact_versions", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("manifest", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("candidate_id", "candidate_version", name="uq_release_candidate_version"),
    )
    op.create_table(
        "release_evaluation_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("release_candidates.id"), nullable=False, index=True),
        sa.Column("decision", sa.String(50), nullable=False, index=True),
        sa.Column("report_version", sa.String(80), nullable=False),
        sa.Column("evaluation_input_hash", sa.String(64), nullable=False, index=True),
        sa.Column("baseline_reference", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("framework_results", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("limitations", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("report_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "release_metric_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("evaluation_id", sa.String(36), sa.ForeignKey("release_evaluation_executions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("metric_name", sa.String(160), nullable=False, index=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("baseline_value", sa.Float(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("denominator", sa.Integer(), nullable=True),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("delta", sa.Float(), nullable=True),
    )
    op.create_table(
        "release_gate_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("evaluation_id", sa.String(36), sa.ForeignKey("release_evaluation_executions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("gate_name", sa.String(120), nullable=False, index=True),
        sa.Column("metric_name", sa.String(160), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text(), nullable=False),
    )
    op.create_table(
        "release_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("evaluation_id", sa.String(36), sa.ForeignKey("release_evaluation_executions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("decision", sa.String(50), nullable=False),
        sa.Column("blocking_reasons", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("evaluation_id", name="uq_release_decision_evaluation"),
    )


def downgrade() -> None:
    op.drop_table("release_decisions")
    op.drop_table("release_gate_results")
    op.drop_table("release_metric_results")
    op.drop_table("release_evaluation_executions")
    op.drop_table("release_candidates")
