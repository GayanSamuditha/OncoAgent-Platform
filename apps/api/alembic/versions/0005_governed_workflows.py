"""Add governed workflow audit records."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_governed_workflows"
down_revision = "0004_model_agnostic_retrieval"
branch_labels = None
depends_on = None

json_type = postgresql.JSONB()


def json_column(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, json_type, nullable=nullable, server_default=sa.text("'{}'::jsonb"))


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("thread_id", sa.String(100), nullable=False),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("actor_id", sa.String(200), nullable=False),
        sa.Column("actor_role", sa.String(40), nullable=False),
        sa.Column("original_request", sa.Text, nullable=False),
        json_column("structured_input"), json_column("structured_plan", True), json_column("retrieval_policy"),
        sa.Column("status", sa.String(40), nullable=False), sa.Column("current_node", sa.String(80), nullable=False),
        sa.Column("approval_id", sa.String(36)), sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("warnings", json_type, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("errors", json_type, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)), json_column("final_result", True),
        sa.UniqueConstraint("thread_id", name="uq_workflow_runs_thread"),
    )
    op.create_index("ix_workflow_runs_thread_id", "workflow_runs", ["thread_id"])
    op.create_index("ix_workflow_runs_dataset_id", "workflow_runs", ["dataset_id"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index("ix_workflow_runs_correlation_id", "workflow_runs", ["correlation_id"])

    op.create_table("workflow_steps", sa.Column("id", sa.String(36), primary_key=True), sa.Column("run_id", sa.String(36), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("node_name", sa.String(80), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("attempt", sa.Integer, nullable=False, server_default="1"), json_column("input_summary"), json_column("output_summary"), sa.Column("error_category", sa.String(60)), sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_workflow_steps_run_id", "workflow_steps", ["run_id"])
    op.create_table("workflow_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("run_id", sa.String(36), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("event_type", sa.String(60), nullable=False), sa.Column("node_name", sa.String(80)), json_column("payload"), sa.Column("correlation_id", sa.String(36), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_workflow_events_run_id", "workflow_events", ["run_id"])
    op.create_index("ix_workflow_events_type", "workflow_events", ["event_type"])
    op.create_index("ix_workflow_events_correlation_id", "workflow_events", ["correlation_id"])
    op.create_table("workflow_tool_calls", sa.Column("id", sa.String(36), primary_key=True), sa.Column("run_id", sa.String(36), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("tool_name", sa.String(100), nullable=False), sa.Column("tool_version", sa.String(40), nullable=False), sa.Column("status", sa.String(30), nullable=False), json_column("sanitized_arguments"), json_column("result_summary"), sa.Column("fallback_reason", sa.Text), sa.Column("error_category", sa.String(60)), sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_workflow_tool_calls_run_id", "workflow_tool_calls", ["run_id"])
    op.create_table("workflow_candidates", sa.Column("id", sa.String(36), primary_key=True), sa.Column("run_id", sa.String(36), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.id"), nullable=False), sa.Column("patient_id", sa.String(36), sa.ForeignKey("patients.id"), nullable=False), sa.Column("document_ids", json_type, nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("retrieval_provider", sa.String(80), nullable=False), sa.Column("retrieval_rank", sa.Integer, nullable=False), sa.Column("retrieval_score", sa.Float), sa.Column("verification_status", sa.String(30), nullable=False), sa.Column("included", sa.Boolean, nullable=False, server_default=sa.false()), sa.UniqueConstraint("run_id", "patient_id", name="uq_workflow_candidate"))
    op.create_index("ix_workflow_candidates_run_id", "workflow_candidates", ["run_id"])
    op.create_index("ix_workflow_candidates_dataset_id", "workflow_candidates", ["dataset_id"])
    op.create_index("ix_workflow_candidates_patient_id", "workflow_candidates", ["patient_id"])
    op.create_table("workflow_evidence", sa.Column("id", sa.String(36), primary_key=True), sa.Column("run_id", sa.String(36), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("patient_id", sa.String(36), sa.ForeignKey("patients.id"), nullable=False), sa.Column("criterion_id", sa.String(100), nullable=False), sa.Column("criterion_description", sa.Text, nullable=False), sa.Column("verification_status", sa.String(30), nullable=False), json_column("structured_value"), sa.Column("source_resource_type", sa.String(80)), sa.Column("source_fhir_resource_id", sa.String(200)), sa.Column("encounter_id", sa.String(36)), sa.Column("effective_timestamp", sa.DateTime(timezone=True)), sa.Column("explanation", sa.Text, nullable=False), sa.Column("verification_tool", sa.String(100), nullable=False), sa.Column("verification_tool_version", sa.String(40), nullable=False), sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.id"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_workflow_evidence_run_id", "workflow_evidence", ["run_id"])
    op.create_index("ix_workflow_evidence_patient_id", "workflow_evidence", ["patient_id"])
    op.create_table("approval_requests", sa.Column("id", sa.String(36), primary_key=True), sa.Column("run_id", sa.String(36), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("requested_by_actor_id", sa.String(200), nullable=False), sa.Column("status", sa.String(30), nullable=False), json_column("payload"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("decided_at", sa.DateTime(timezone=True)))
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])
    op.create_table("approval_decisions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("approval_id", sa.String(36), sa.ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False), sa.Column("run_id", sa.String(36), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("actor_id", sa.String(200), nullable=False), sa.Column("actor_role", sa.String(40), nullable=False), sa.Column("decision", sa.String(30), nullable=False), sa.Column("comment", sa.Text), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("approval_id", name="uq_approval_decision"))
    op.create_index("ix_approval_decisions_approval_id", "approval_decisions", ["approval_id"])
    op.create_table("policy_decisions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("run_id", sa.String(36), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("stage", sa.String(30), nullable=False), sa.Column("decision", sa.String(30), nullable=False), sa.Column("reason", sa.Text, nullable=False), json_column("details"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_policy_decisions_run_id", "policy_decisions", ["run_id"])
    op.create_table("workflow_lineage", sa.Column("id", sa.String(36), primary_key=True), sa.Column("run_id", sa.String(36), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("entity_type", sa.String(60), nullable=False), sa.Column("entity_id", sa.String(200), nullable=False), sa.Column("entity_version", sa.String(100), nullable=False), json_column("metadata_json"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_workflow_lineage_run_id", "workflow_lineage", ["run_id"])


def downgrade() -> None:
    for table in ("workflow_lineage", "policy_decisions", "approval_decisions", "approval_requests", "workflow_evidence", "workflow_candidates", "workflow_tool_calls", "workflow_events", "workflow_steps", "workflow_runs"):
        op.drop_table(table)
