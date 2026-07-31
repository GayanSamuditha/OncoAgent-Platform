"""Add security readiness evidence and audit-integrity fields."""

import sqlalchemy as sa
from alembic import op

revision = "0015_security_privacy_readiness"
down_revision = "0014_performance_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("identity_access_decisions", sa.Column("canonical_digest", sa.String(64), nullable=True))
    op.add_column("identity_access_decisions", sa.Column("previous_digest", sa.String(64), nullable=True))
    op.add_column("identity_access_decisions", sa.Column("integrity_version", sa.String(40), nullable=True))
    op.create_index("ix_identity_access_decisions_canonical_digest", "identity_access_decisions", ["canonical_digest"])
    op.create_table(
        "security_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assessment_id", sa.String(120), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("report_reference", sa.String(500), nullable=True),
        sa.Column("findings_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("gates", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("limitations", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("assessment_id", name="uq_security_assessment_id"),
    )
    op.create_index("ix_security_assessments_assessment_id", "security_assessments", ["assessment_id"])
    op.create_index("ix_security_assessments_status", "security_assessments", ["status"])
    op.create_table(
        "security_findings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assessment_id", sa.String(36), sa.ForeignKey("security_assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_id", sa.String(120), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(30), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("owner", sa.String(120), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
    )
    op.create_index("ix_security_findings_assessment_id", "security_findings", ["assessment_id"])
    op.create_index("ix_security_findings_finding_id", "security_findings", ["finding_id"])
    op.create_index("ix_security_findings_severity", "security_findings", ["severity"])
    op.create_index("ix_security_findings_state", "security_findings", ["state"])
    op.create_table(
        "security_retention_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("rule_id", sa.String(120), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("deletion_method", sa.String(200), nullable=False),
        sa.Column("exception_behavior", sa.Text(), nullable=False),
        sa.Column("owner", sa.String(120), nullable=False),
        sa.Column("review_date", sa.Date(), nullable=False),
        sa.UniqueConstraint("rule_id", name="uq_security_retention_rule"),
    )
    op.create_index("ix_security_retention_rules_rule_id", "security_retention_rules", ["rule_id"])


def downgrade() -> None:
    op.drop_index("ix_security_retention_rules_rule_id", table_name="security_retention_rules")
    op.drop_table("security_retention_rules")
    op.drop_index("ix_security_findings_state", table_name="security_findings")
    op.drop_index("ix_security_findings_severity", table_name="security_findings")
    op.drop_index("ix_security_findings_finding_id", table_name="security_findings")
    op.drop_index("ix_security_findings_assessment_id", table_name="security_findings")
    op.drop_table("security_findings")
    op.drop_index("ix_security_assessments_status", table_name="security_assessments")
    op.drop_index("ix_security_assessments_assessment_id", table_name="security_assessments")
    op.drop_table("security_assessments")
    op.drop_index("ix_identity_access_decisions_canonical_digest", table_name="identity_access_decisions")
    op.drop_column("identity_access_decisions", "integrity_version")
    op.drop_column("identity_access_decisions", "previous_digest")
    op.drop_column("identity_access_decisions", "canonical_digest")
