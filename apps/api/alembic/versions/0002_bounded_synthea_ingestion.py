"""Add bounded Synthea ingestion schema."""
from alembic import op

from app.db.base import Base
import app.models  # noqa: F401

revision = "0002_bounded_synthea_ingestion"
down_revision = "0001_phase0_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The model metadata is the single source of truth for this additive foundation schema.
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


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
