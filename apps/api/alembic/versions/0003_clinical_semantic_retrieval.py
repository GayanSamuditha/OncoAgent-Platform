"""Add clinical document and embedding storage."""
from alembic import op
from app.db.base import Base
import app.models  # noqa: F401

revision = "0003_clinical_semantic_retrieval"
down_revision = "0002_bounded_synthea_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Keep the revision boundary explicit.  Creating all imported models here
    # would pre-create workflow, identity, and release tables owned by later
    # migrations on a clean installation.
    retrieval_tables = [
        "clinical_documents",
        "clinical_document_chunks",
        "clinical_embeddings",
        "indexing_runs",
    ]
    Base.metadata.create_all(
        bind=op.get_bind(),
        tables=[Base.metadata.tables[name] for name in retrieval_tables],
        checkfirst=True,
    )


def downgrade() -> None:
    for table in ("indexing_runs", "clinical_embeddings", "clinical_document_chunks", "clinical_documents"):
        op.drop_table(table)
