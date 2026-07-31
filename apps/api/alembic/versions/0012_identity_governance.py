"""Add local OIDC-compatible identity and authorization records."""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0012_identity_governance"
down_revision = "0011_temporal_execution"
branch_labels = None
depends_on = None


ROLES = {
    "researcher": "Creates bounded synthetic research workflows.",
    "reviewer": "Reviews assigned synthetic research outputs.",
    "governance_officer": "Inspects governance and policy decisions.",
    "platform_operator": "Operates bounded platform and Temporal controls.",
    "auditor": "Reads append-only audit and lineage records.",
    "administrator": "Administers local identity configuration.",
}
PERMISSIONS = {
    "workflow:create": "Create a governed workflow.",
    "workflow:read-own": "Read workflows created by the actor.",
    "workflow:read-all": "Read all permitted workflows.",
    "workflow:cancel-own": "Cancel an owned workflow.",
    "workflow:cancel-any": "Cancel a permitted workflow.",
    "review:read-assigned": "Read assigned review requests.",
    "review:decide": "Submit an eligible review decision.",
    "review:assign": "Assign reviewers.",
    "evidence:read": "Read structured evidence.",
    "provenance:read": "Read provenance metadata.",
    "audit:read": "Read audit records.",
    "governance:read": "Read governance status.",
    "evaluation:read": "Read evaluation results.",
    "resilience:read": "Read resilience certifications.",
    "temporal:read": "Read Temporal execution status.",
    "operator:manage-failure": "Manage development-only failure controls.",
    "identity:manage": "Manage local users, roles, and grants.",
    "dataset:use": "Use an explicitly granted synthetic dataset.",
}
ROLE_PERMISSIONS = {
    "researcher": {"workflow:create", "workflow:read-own", "workflow:cancel-own", "evidence:read", "provenance:read", "evaluation:read", "dataset:use"},
    "reviewer": {"workflow:read-own", "review:read-assigned", "review:decide", "evidence:read", "provenance:read", "evaluation:read", "dataset:use"},
    "governance_officer": {"audit:read", "governance:read", "evaluation:read", "resilience:read", "provenance:read"},
    "platform_operator": {"workflow:read-all", "workflow:cancel-any", "temporal:read", "operator:manage-failure", "governance:read"},
    "auditor": {"audit:read", "governance:read", "provenance:read", "evaluation:read", "resilience:read"},
    "administrator": set(PERMISSIONS),
}


def upgrade() -> None:
    op.create_table(
        "identity_users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("external_subject", sa.String(255), nullable=False),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_authenticated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("issuer", "external_subject", name="uq_identity_subject"),
    )
    op.create_table(
        "identity_roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_table(
        "identity_permissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_table(
        "identity_user_roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("identity_users.id", ondelete="CASCADE"), index=True),
        sa.Column("role_id", sa.String(36), sa.ForeignKey("identity_roles.id", ondelete="CASCADE"), index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "role_id", name="uq_identity_user_role"),
    )
    op.create_table(
        "identity_role_permissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("role_id", sa.String(36), sa.ForeignKey("identity_roles.id", ondelete="CASCADE"), index=True),
        sa.Column("permission_id", sa.String(36), sa.ForeignKey("identity_permissions.id", ondelete="CASCADE"), index=True),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_identity_role_permission"),
    )
    op.create_table(
        "identity_dataset_grants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("identity_users.id", ondelete="CASCADE"), index=True),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.id", ondelete="CASCADE"), index=True),
        sa.Column("grant_type", sa.String(40), nullable=False, server_default="synthetic_development"),
        sa.Column("granted_by", sa.String(36), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "dataset_id", name="uq_identity_dataset_grant"),
    )
    op.create_table(
        "identity_reviewer_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("identity_users.id", ondelete="CASCADE"), index=True),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.id", ondelete="CASCADE"), index=True),
        sa.Column("review_type", sa.String(80), nullable=False, server_default="synthetic_cohort"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "dataset_id", name="uq_identity_reviewer_assignment"),
    )
    op.create_table(
        "identity_access_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(120), nullable=False, index=True),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", sa.String(200), nullable=True),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("correlation_id", sa.String(100), nullable=True, index=True),
        sa.Column("trace_id", sa.String(32), nullable=True, index=True),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    role_table = sa.table("identity_roles", sa.column("id", sa.String), sa.column("name", sa.String), sa.column("description", sa.Text))
    permission_table = sa.table("identity_permissions", sa.column("id", sa.String), sa.column("name", sa.String), sa.column("description", sa.Text))
    role_rows = [{"id": str(uuid4()), "name": name, "description": description} for name, description in ROLES.items()]
    permission_rows = [{"id": str(uuid4()), "name": name, "description": description} for name, description in PERMISSIONS.items()]
    op.bulk_insert(role_table, role_rows)
    op.bulk_insert(permission_table, permission_rows)
    link_table = sa.table("identity_role_permissions", sa.column("id", sa.String), sa.column("role_id", sa.String), sa.column("permission_id", sa.String))
    role_ids = {row["name"]: row["id"] for row in role_rows}
    permission_ids = {row["name"]: row["id"] for row in permission_rows}
    op.bulk_insert(link_table, [{"id": str(uuid4()), "role_id": role_ids[role], "permission_id": permission_ids[permission]} for role, permissions in ROLE_PERMISSIONS.items() for permission in permissions])


def downgrade() -> None:
    op.drop_table("identity_access_decisions")
    op.drop_table("identity_reviewer_assignments")
    op.drop_table("identity_dataset_grants")
    op.drop_table("identity_role_permissions")
    op.drop_table("identity_user_roles")
    op.drop_table("identity_permissions")
    op.drop_table("identity_roles")
    op.drop_table("identity_users")
