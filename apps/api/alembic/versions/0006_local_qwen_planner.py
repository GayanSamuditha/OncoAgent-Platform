"""Add local planner lineage."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_local_qwen_planner"
down_revision = "0005_governed_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflow_runs", sa.Column("planner_lineage", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("workflow_runs", "planner_lineage")
