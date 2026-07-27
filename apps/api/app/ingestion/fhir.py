from datetime import UTC, datetime
from typing import Any

SUPPORTED_RESOURCE_TYPES = {
    "Patient",
    "Encounter",
    "Condition",
    "Observation",
    "Procedure",
    "MedicationRequest",
    "DiagnosticReport",
    "ImagingStudy",
}


def resource_entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    entries = bundle.get("entry", [])
    if not isinstance(entries, list):
        return []
    return [
        entry["resource"]
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("resource"), dict)
    ]


def resource_reference_id(reference: Any) -> str | None:
    if not isinstance(reference, str) or not reference:
        return None
    if reference.startswith("urn:uuid:"):
        return reference.removeprefix("urn:uuid:").split("?")[0] or None
    value = reference.split("/")[-1].split("?")[0]
    return value or None


def reference_id(value: Any) -> str | None:
    if isinstance(value, dict):
        return resource_reference_id(value.get("reference"))
    return resource_reference_id(value)


def patient_reference(resource: dict[str, Any]) -> str | None:
    if resource.get("resourceType") == "Patient":
        return resource.get("id")
    return reference_id(resource.get("subject")) or reference_id(resource.get("patient"))


def encounter_reference(resource: dict[str, Any]) -> str | None:
    return reference_id(resource.get("encounter"))


def coding(value: Any) -> tuple[str | None, str | None, str | None]:
    if not isinstance(value, dict):
        return None, None, None
    codings = value.get("coding")
    if not isinstance(codings, list) or not codings or not isinstance(codings[0], dict):
        return None, None, value.get("text") if isinstance(value.get("text"), str) else None
    first = codings[0]
    return first.get("system"), first.get("code"), first.get("display") or value.get("text")


def first_coding(
    resource: dict[str, Any], field: str = "code"
) -> tuple[str | None, str | None, str | None]:
    return coding(resource.get(field))


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = value
    if len(candidate) == 10:
        candidate = f"{candidate}T00:00:00+00:00"
    elif candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def period(
    resource: dict[str, Any], field: str = "period"
) -> tuple[datetime | None, datetime | None]:
    value = resource.get(field)
    if not isinstance(value, dict):
        return None, None
    return parse_datetime(value.get("start")), parse_datetime(value.get("end"))


def extract_value(value: Any) -> tuple[float | None, str | None, str | None]:
    if not isinstance(value, dict):
        return None, None, None
    if isinstance(value.get("valueQuantity"), dict):
        quantity = value["valueQuantity"]
        number = quantity.get("value")
        return (
            float(number) if isinstance(number, (int, float)) else None,
            None,
            quantity.get("unit"),
        )
    for key in ("valueString", "valueCodeableConcept", "valueCode", "valueBoolean", "valueInteger"):
        if key not in value:
            continue
        candidate = value[key]
        if key == "valueCodeableConcept":
            _, _, display = coding(candidate)
            return None, display, None
        return None, str(candidate), None
    return None, None, None


def category_display(resource: dict[str, Any]) -> str | None:
    categories = resource.get("category")
    if not isinstance(categories, list) or not categories:
        return None
    _, _, display = coding(categories[0])
    return display


def modality_codes(resource: dict[str, Any]) -> list[dict[str, Any]]:
    series = resource.get("series")
    if not isinstance(series, list):
        return []
    values: list[dict[str, Any]] = []
    for item in series:
        if isinstance(item, dict) and isinstance(item.get("modality"), dict):
            modality = item["modality"]
            values.append(
                {
                    "system": modality.get("system"),
                    "code": modality.get("code"),
                    "display": modality.get("display"),
                }
            )
    return values
