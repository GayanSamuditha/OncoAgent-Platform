"""Add provider-specific model lineage for dense retrieval."""
from alembic import op
import sqlalchemy as sa

revision = "0004_model_agnostic_retrieval"
down_revision = "0003_clinical_semantic_retrieval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        "clinical_documents": [
            ("title", sa.Text(), ""),
            ("title_sha256", sa.String(64), ""),
            ("body_sha256", sa.String(64), ""),
        ],
        "clinical_embeddings": [
            ("provider_id", sa.String(80), "bioclinicalbert"),
            ("query_model_name", sa.String(200), ""),
            ("document_model_name", sa.String(200), ""),
            ("query_model_revision", sa.String(200), ""),
            ("document_model_revision", sa.String(200), ""),
            ("normalization_strategy", sa.String(40), "l2"),
            ("query_max_length", sa.Integer(), 64),
            ("document_max_length", sa.Integer(), 512),
            ("representation_version", sa.String(40), "clinical-document-v1"),
        ],
        "indexing_runs": [
            ("provider_id", sa.String(80), "bioclinicalbert"),
            ("document_model_name", sa.String(200), ""),
            ("document_model_revision", sa.String(200), ""),
        ],
    }
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, entries in columns.items():
        existing = {col["name"] for col in inspector.get_columns(table)}
        for name, type_, default in entries:
            if name not in existing:
                op.add_column(table, sa.Column(name, type_, nullable=False, server_default=sa.text(f"'{default}'") if isinstance(default, str) else sa.text(str(default))))
                op.alter_column(table, name, server_default=None)


def downgrade() -> None:
    for table, names in {
        "indexing_runs": ["document_model_revision", "document_model_name", "provider_id"],
        "clinical_embeddings": ["representation_version", "document_max_length", "query_max_length", "normalization_strategy", "document_model_revision", "query_model_revision", "document_model_name", "query_model_name", "provider_id"],
        "clinical_documents": ["body_sha256", "title_sha256", "title"],
    }.items():
        for name in names:
            op.drop_column(table, name)
