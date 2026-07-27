from datetime import UTC

from app.ingestion.fhir import (
    category_display,
    extract_value,
    parse_datetime,
    patient_reference,
    resource_reference_id,
)


def test_reference_and_date_helpers_support_common_fhir_forms() -> None:
    assert resource_reference_id("Patient/p-1") == "p-1"
    assert resource_reference_id("urn:uuid:p-1") == "p-1"
    assert (
        patient_reference({"resourceType": "Observation", "subject": {"reference": "Patient/p-1"}})
        == "p-1"
    )
    parsed = parse_datetime("2024-01-01T12:00:00Z")
    assert parsed is not None and parsed.tzinfo == UTC


def test_observation_values_and_categories() -> None:
    numeric, text, unit = extract_value({"valueQuantity": {"value": 70.5, "unit": "kg"}})
    assert numeric == 70.5
    assert text is None
    assert unit == "kg"
    _, text, _ = extract_value({"valueString": "stable"})
    assert text == "stable"
    assert (
        category_display({"category": [{"coding": [{"display": "vital-signs"}]}]}) == "vital-signs"
    )
