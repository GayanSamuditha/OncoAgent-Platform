import os
import tarfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.ingestion.service import import_synthea_sample
from app.models.ingestion import FhirResource, Patient


@pytest.mark.skipif(
    not os.environ.get("ONCOAGENT_TEST_DATABASE_URL"),
    reason="requires explicit integration database",
)
def test_reimport_is_idempotent(tmp_path: Path) -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "sample_bundle.json"
    archive = tmp_path / "sample.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        output.add(fixture, arcname="output_1/fhir/00/000/patient.json")
    engine = create_engine(os.environ["ONCOAGENT_TEST_DATABASE_URL"])
    dataset_name = f"test-idempotent-{uuid.uuid4()}"
    with Session(engine) as session:
        first = import_synthea_sample(session, archive, dataset_name, 1)
        second = import_synthea_sample(session, archive, dataset_name, 1)
        assert first.imported_patient_count == 1
        assert second.imported_patient_count == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(Patient)
                .where(Patient.dataset_id == first.dataset_id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(FhirResource)
                .where(FhirResource.dataset_id == first.dataset_id)
            )
            == 8
        )
