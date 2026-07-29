"""Add bounded Synthea ingestion schema."""
from alembic import op

from app.db.base import Base
import app.models  # noqa: F401

revision = "0002_bounded_synthea_ingestion"
down_revision = "0001_phase0_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only create the ingestion tables owned by this revision.  Importing the
    # complete model registry here would also create tables introduced by
    # later revisions, causing those revisions to fail on a clean database.
    ingestion_tables = [
        "datasets",
        "patients",
        "conditions",
        "observations",
        "procedures",
        "medication_requests",
        "diagnostic_reports",
        "imaging_studies",
        "encounters",
        "fhir_resources",
        "ingestion_runs",
    ]
    Base.metadata.create_all(
        bind=op.get_bind(),
        tables=[Base.metadata.tables[name] for name in ingestion_tables],
        checkfirst=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in (
        "fhir_resources",
        "imaging_studies",
        "diagnostic_reports",
        "medication_requests",
        "procedures",
        "observations",
        "conditions",
        "encounters",
        "patients",
        "ingestion_runs",
        "datasets",
    ):
        op.drop_table(table_name, if_exists=True)
