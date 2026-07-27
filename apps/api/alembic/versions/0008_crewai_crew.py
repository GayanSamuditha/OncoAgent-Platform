"""Add governed downstream CrewAI run records."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_crewai_crew"
down_revision = "0007_mcp_gateway"
branch_labels = None
depends_on = None

JSON = postgresql.JSONB


def _common_run_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("actor_id", sa.String(200), nullable=False), sa.Column("actor_role", sa.String(40), nullable=False),
        sa.Column("mcp_client_id", sa.String(120), nullable=False), sa.Column("crew_name", sa.String(120), nullable=False),
        sa.Column("crew_version", sa.String(40), nullable=False), sa.Column("crewai_version", sa.String(40), nullable=False),
        sa.Column("process_type", sa.String(30), nullable=False), sa.Column("model_tag", sa.String(120), nullable=False),
        sa.Column("model_digest", sa.String(128)), sa.Column("status", sa.String(40), nullable=False),
        sa.Column("current_task", sa.String(80)), sa.Column("research_question", sa.Text(), nullable=False),
        sa.Column("structured_criteria", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("sanitized_input", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output_summary", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("idempotency_key", sa.String(200)), sa.Column("error_category", sa.String(80)), sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table("crew_runs", *_common_run_columns(), sa.UniqueConstraint("idempotency_key", name="uq_crew_runs_idempotency_key"))
    op.create_index("ix_crew_runs_dataset_id", "crew_runs", ["dataset_id"])
    op.create_index("ix_crew_runs_correlation_id", "crew_runs", ["correlation_id"])
    op.create_index("ix_crew_runs_status", "crew_runs", ["status"])
    op.create_table("crew_agents", sa.Column("id", sa.String(36), primary_key=True), sa.Column("crew_run_id", sa.String(36), sa.ForeignKey("crew_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("role", sa.String(100), nullable=False), sa.Column("version", sa.String(40), nullable=False), sa.Column("allowed_tools", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.create_index("ix_crew_agents_crew_run_id", "crew_agents", ["crew_run_id"])
    op.create_table("crew_tasks", sa.Column("id", sa.String(36), primary_key=True), sa.Column("crew_run_id", sa.String(36), sa.ForeignKey("crew_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("task_name", sa.String(100), nullable=False), sa.Column("task_version", sa.String(40), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("agent_role", sa.String(100), nullable=False), sa.Column("output_summary", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("latency_ms", sa.Float()), sa.Column("error_category", sa.String(80)), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("crew_run_id", "task_name", name="uq_crew_tasks_run_name"))
    op.create_index("ix_crew_tasks_crew_run_id", "crew_tasks", ["crew_run_id"])
    op.create_table("crew_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("crew_run_id", sa.String(36), sa.ForeignKey("crew_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("event_type", sa.String(60), nullable=False), sa.Column("task_name", sa.String(100)), sa.Column("payload", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_crew_events_crew_run_id", "crew_events", ["crew_run_id"])
    op.create_index("ix_crew_events_event_type", "crew_events", ["event_type"])
    op.create_table("crew_outputs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("crew_run_id", sa.String(36), sa.ForeignKey("crew_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("output_type", sa.String(60), nullable=False), sa.Column("schema_version", sa.String(40), nullable=False), sa.Column("output_json", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("crew_run_id", "output_type", name="uq_crew_outputs_run_type"))
    op.create_index("ix_crew_outputs_crew_run_id", "crew_outputs", ["crew_run_id"])
    op.create_table("crew_reviews", sa.Column("id", sa.String(36), primary_key=True), sa.Column("crew_run_id", sa.String(36), sa.ForeignKey("crew_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("reviewer_id", sa.String(200)), sa.Column("reviewer_role", sa.String(40)), sa.Column("decision", sa.String(50)), sa.Column("comment", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("decided_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("crew_run_id", name="uq_crew_reviews_run"))
    op.create_index("ix_crew_reviews_crew_run_id", "crew_reviews", ["crew_run_id"])
    op.create_table("crew_lineage", sa.Column("id", sa.String(36), primary_key=True), sa.Column("crew_run_id", sa.String(36), sa.ForeignKey("crew_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("config_version", sa.String(40), nullable=False), sa.Column("config_hash", sa.String(64), nullable=False), sa.Column("mcp_protocol_version", sa.String(40), nullable=False), sa.Column("mcp_server_version", sa.String(40), nullable=False), sa.Column("mcp_request_ids", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("tool_names", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("retrieval_lineage", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("token_usage", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.create_index("ix_crew_lineage_crew_run_id", "crew_lineage", ["crew_run_id"])


def downgrade() -> None:
    for table in ("crew_lineage", "crew_reviews", "crew_outputs", "crew_events", "crew_tasks", "crew_agents", "crew_runs"):
        op.drop_table(table)
