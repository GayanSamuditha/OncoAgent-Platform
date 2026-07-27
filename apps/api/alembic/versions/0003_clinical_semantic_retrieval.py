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
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for table in ("indexing_runs", "clinical_embeddings", "clinical_document_chunks", "clinical_documents"):
        op.drop_table(table)
