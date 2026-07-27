import json
import tarfile
from pathlib import Path

import pytest

from app.ingestion.service import HARD_PATIENT_LIMIT, selected_bundles, validate_patient_limit


def make_archive(tmp_path: Path) -> Path:
    fixture = Path(__file__).parents[1] / "fixtures" / "sample_bundle.json"
    archive_path = tmp_path / "sample.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(fixture, arcname="output_1/fhir/00/000/patient.json")
    return archive_path


def test_streaming_selection_is_bounded_and_deterministic(tmp_path: Path) -> None:
    archive = make_archive(tmp_path)
    first = list(selected_bundles(archive, 1))
    second = list(selected_bundles(archive, 1))
    assert [item[0] for item in first] == [item[0] for item in second]
    assert json.loads(first[0][1])["resourceType"] == "Bundle"


def test_patient_limit_enforcement() -> None:
    with pytest.raises(ValueError):
        validate_patient_limit(HARD_PATIENT_LIMIT + 1)
    validate_patient_limit(HARD_PATIENT_LIMIT + 1, unsafe_override=True)
