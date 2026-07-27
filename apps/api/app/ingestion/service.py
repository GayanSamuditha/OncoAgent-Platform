import hashlib
import json
import os
import re
import tarfile
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingestion.fhir import (
    SUPPORTED_RESOURCE_TYPES,
    category_display,
    extract_value,
    first_coding,
    modality_codes,
    parse_datetime,
    patient_reference,
    period,
    resource_entries,
    resource_reference_id,
)
from app.models.ingestion import (
    Condition,
    Dataset,
    DiagnosticReport,
    Encounter,
    FhirResource,
    ImagingStudy,
    IngestionRun,
    MedicationRequest,
    Observation,
    Patient,
    Procedure,
)

DEFAULT_PATIENT_LIMIT = 100
HARD_PATIENT_LIMIT = 1000
SAMPLE_POLICY = "First N Patient-containing FHIR bundles in deterministic archive member order."


@dataclass
class IngestionSummary:
    dataset_id: str
    ingestion_run_id: str
    status: str
    processed_bundle_count: int
    imported_patient_count: int
    imported_resource_count: int
    skipped_resource_count: int
    error_count: int
    resource_counts: dict[str, int]


def validate_patient_limit(limit: int, unsafe_override: bool = False) -> None:
    if limit < 1:
        raise ValueError("patient limit must be at least 1")
    if limit > HARD_PATIENT_LIMIT and not unsafe_override:
        raise ValueError(
            f"patient limit cannot exceed {HARD_PATIENT_LIMIT} without --unsafe-override"
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_path_hash(path: Path) -> str:
    return hashlib.sha256(str(path.expanduser().resolve()).encode()).hexdigest()


def archive_members(path: Path) -> Iterator[tuple[str, bytes]]:
    with tarfile.open(path, mode="r|gz") as archive:
        for member in archive:
            if (
                not member.isfile()
                or not member.name.endswith(".json")
                or "/fhir/" not in member.name
            ):
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            yield member.name, extracted.read()


def selected_bundles(path: Path, limit: int) -> Iterator[tuple[str, bytes, dict[str, Any]]]:
    selected = 0
    for member_path, raw_bytes in archive_members(path):
        try:
            bundle = json.loads(raw_bytes)
        except json.JSONDecodeError:
            continue
        if not isinstance(bundle, dict) or not any(
            resource.get("resourceType") == "Patient" for resource in resource_entries(bundle)
        ):
            continue
        yield member_path, raw_bytes, bundle
        selected += 1
        if selected >= limit:
            return


def synthea_version(resources: list[dict[str, Any]]) -> str | None:
    for resource in resources:
        div = (
            resource.get("text", {}).get("div") if isinstance(resource.get("text"), dict) else None
        )
        if isinstance(div, str):
            match = re.search(r"Version identifier:\s*([^<]+)", div)
            if match:
                return match.group(1).strip()
    return None


def resolved_reference(value: Any, resources: dict[str, dict[str, Any]]) -> str | None:
    reference = value.get("reference") if isinstance(value, dict) else value
    if not isinstance(reference, str):
        return None
    direct = resource_reference_id(reference)
    if direct in resources:
        return resources[direct].get("id")
    for full_url, resource in resources.items():
        if reference == full_url or reference == f"urn:uuid:{resource.get('id')}":
            return resource.get("id")
    return direct


def existing_by_fhir(session: Session, model: Any, dataset_id: str, fhir_id: str) -> Any | None:
    return session.scalar(
        select(model).where(model.dataset_id == dataset_id, model.fhir_id == fhir_id)
    )


def add_fhir_resource(
    session: Session,
    dataset_id: str,
    patient_db_id: str | None,
    resource: dict[str, Any],
    archive_name: str,
    member_path: str,
    member_hash: str,
) -> bool:
    resource_type = resource.get("resourceType")
    fhir_id = resource.get("id")
    if (
        not isinstance(resource_type, str)
        or resource_type not in SUPPORTED_RESOURCE_TYPES
        or not isinstance(fhir_id, str)
    ):
        return False
    existing = session.scalar(
        select(FhirResource).where(
            FhirResource.dataset_id == dataset_id,
            FhirResource.resource_type == resource_type,
            FhirResource.fhir_id == fhir_id,
        )
    )
    if existing is not None:
        return False
    session.add(
        FhirResource(
            id=str(uuid.uuid4()),
            dataset_id=dataset_id,
            patient_id=patient_db_id,
            resource_type=resource_type,
            fhir_id=fhir_id,
            source_archive_name=archive_name,
            source_member_path=member_path,
            source_member_sha256=member_hash,
            raw_resource_json=resource.get("_raw_resource", resource),
        )
    )
    return True


def import_bundle(
    session: Session,
    dataset_id: str,
    archive_name: str,
    member_path: str,
    raw_bytes: bytes,
    bundle: dict[str, Any],
) -> tuple[int, int, dict[str, int]]:
    resources: list[dict[str, Any]] = []
    for entry_index, entry in enumerate(bundle.get("entry", [])):
        if not isinstance(entry, dict) or not isinstance(entry.get("resource"), dict):
            continue
        original = entry["resource"]
        processed = dict(original)
        if not isinstance(processed.get("id"), str):
            full_url = entry.get("fullUrl")
            if isinstance(full_url, str):
                processed["id"] = resource_reference_id(full_url) or full_url
            else:
                identity = json.dumps(original, sort_keys=True, separators=(",", ":"))
                processed["id"] = (
                    "synthetic-"
                    + hashlib.sha256(f"{member_path}:{entry_index}:{identity}".encode()).hexdigest()
                )
        processed["_raw_resource"] = original
        resources.append(processed)
    by_reference: dict[str, dict[str, Any]] = {}
    for resource in resources:
        if isinstance(resource.get("id"), str):
            by_reference[resource["id"]] = resource
        for entry in bundle.get("entry", []):
            if (
                isinstance(entry, dict)
                and entry.get("resource") is resource
                and isinstance(entry.get("fullUrl"), str)
            ):
                by_reference[entry["fullUrl"]] = resource

    patient_resources = [
        r for r in resources if r.get("resourceType") == "Patient" and isinstance(r.get("id"), str)
    ]
    if not patient_resources:
        return 0, 0, {}
    patient_resource = patient_resources[0]
    patient_fhir_id = patient_resource["id"]
    patient = existing_by_fhir(session, Patient, dataset_id, patient_fhir_id)
    if patient is None:
        patient = Patient(
            id=str(uuid.uuid4()),
            dataset_id=dataset_id,
            fhir_id=patient_fhir_id,
            birth_date=patient_resource.get("birthDate"),
            gender=patient_resource.get("gender"),
            deceased=patient_resource.get("deceasedBoolean")
            if isinstance(patient_resource.get("deceasedBoolean"), bool)
            else None,
            source_resource_id=patient_fhir_id,
        )
        session.add(patient)
        session.flush()
        new_patients = 1
    else:
        new_patients = 0

    resource_counts: dict[str, int] = {}
    new_resources = 0
    member_hash = hashlib.sha256(raw_bytes).hexdigest()
    add_fhir_resource(
        session, dataset_id, patient.id, patient_resource, archive_name, member_path, member_hash
    )
    encounter_ids: dict[str, str] = {}

    for resource in resources:
        if resource.get("resourceType") != "Encounter" or not isinstance(resource.get("id"), str):
            continue
        fhir_id = resource["id"]
        encounter = existing_by_fhir(session, Encounter, dataset_id, fhir_id)
        if encounter is None:
            start, end = period(resource)
            system, code, display = first_coding(resource, "type")
            cls = resource.get("class")
            encounter = Encounter(
                id=str(uuid.uuid4()),
                dataset_id=dataset_id,
                patient_id=patient.id,
                fhir_id=fhir_id,
                status=resource.get("status"),
                encounter_class=cls.get("code") if isinstance(cls, dict) else None,
                encounter_type_code=code,
                encounter_type_display=display,
                start_time=start,
                end_time=end,
                source_resource_id=fhir_id,
            )
            session.add(encounter)
            session.flush()
            add_fhir_resource(
                session, dataset_id, patient.id, resource, archive_name, member_path, member_hash
            )
            new_resources += 1
            resource_counts["Encounter"] = resource_counts.get("Encounter", 0) + 1
        encounter_ids[fhir_id] = encounter.id

    for resource in resources:
        resource_type = resource.get("resourceType")
        fhir_id = resource.get("id")
        if (
            resource_type == "Patient"
            or resource_type == "Encounter"
            or not isinstance(fhir_id, str)
        ):
            continue
        patient_fhir_id = (
            resolved_reference(resource.get("subject") or resource.get("patient"), by_reference)
            or patient_reference(resource)
            or patient.fhir_id
        )
        if patient_fhir_id != patient.fhir_id:
            continue
        encounter_fhir_id = resolved_reference(resource.get("encounter"), by_reference)
        encounter_id = encounter_ids.get(encounter_fhir_id) if encounter_fhir_id else None
        common = dict(
            id=str(uuid.uuid4()),
            dataset_id=dataset_id,
            patient_id=patient.id,
            encounter_id=encounter_id,
            fhir_id=fhir_id,
            source_resource_id=fhir_id,
        )
        resource_type_name = resource_type if isinstance(resource_type, str) else None
        if resource_type_name is None:
            continue
        existing_model = {
            "Condition": Condition,
            "Observation": Observation,
            "Procedure": Procedure,
            "MedicationRequest": MedicationRequest,
            "DiagnosticReport": DiagnosticReport,
            "ImagingStudy": ImagingStudy,
        }.get(resource_type_name)
        if existing_model is None:
            continue
        if existing_by_fhir(session, existing_model, dataset_id, fhir_id) is not None:
            add_fhir_resource(
                session, dataset_id, patient.id, resource, archive_name, member_path, member_hash
            )
            continue
        system, code, display = first_coding(resource)
        row: Any
        if resource_type_name == "Condition":
            start, _ = period(resource, "onsetPeriod")
            end, _ = period(resource, "abatementPeriod")
            row = Condition(
                **common,
                clinical_status=resource.get("clinicalStatus", {}).get("text")
                if isinstance(resource.get("clinicalStatus"), dict)
                else None,
                verification_status=resource.get("verificationStatus", {}).get("text")
                if isinstance(resource.get("verificationStatus"), dict)
                else None,
                code_system=system,
                code=code,
                display=display,
                onset_time=start or parse_datetime(resource.get("onsetDateTime")),
                abatement_time=end or parse_datetime(resource.get("abatementDateTime")),
            )
        elif resource_type_name == "Observation":
            numeric, text_value, unit = extract_value(
                resource.get("valueQuantity")
                and {"valueQuantity": resource.get("valueQuantity")}
                or resource
            )
            row = Observation(
                **common,
                status=resource.get("status"),
                category=category_display(resource),
                code_system=system,
                code=code,
                display=display,
                value_numeric=numeric,
                value_text=text_value,
                unit=unit,
                effective_time=parse_datetime(resource.get("effectiveDateTime")),
            )
        elif resource_type_name == "Procedure":
            start, end = period(resource, "performedPeriod")
            row = Procedure(
                **common,
                status=resource.get("status"),
                code_system=system,
                code=code,
                display=display,
                performed_start=start or parse_datetime(resource.get("performedDateTime")),
                performed_end=end,
            )
        elif resource_type_name == "MedicationRequest":
            medication = resource.get("medicationCodeableConcept")
            med_system, med_code, med_display = (
                first_coding({"code": medication})
                if isinstance(medication, dict)
                else first_coding(resource)
            )
            row = MedicationRequest(
                **common,
                status=resource.get("status"),
                intent=resource.get("intent"),
                code_system=med_system,
                code=med_code,
                display=med_display,
                authored_on=parse_datetime(resource.get("authoredOn")),
            )
        elif resource_type_name == "DiagnosticReport":
            row = DiagnosticReport(
                **common,
                status=resource.get("status"),
                code_system=system,
                code=code,
                display=display,
                effective_time=parse_datetime(resource.get("effectiveDateTime")),
                issued_time=parse_datetime(resource.get("issued")),
            )
        else:
            row = ImagingStudy(
                **common,
                status=resource.get("status"),
                started_at=parse_datetime(resource.get("started")),
                modality_codes=modality_codes(resource),
                description=resource.get("description"),
            )
        session.add(row)
        new_resources += 1
        resource_counts[resource_type_name] = resource_counts.get(resource_type_name, 0) + 1
        add_fhir_resource(
            session, dataset_id, patient.id, resource, archive_name, member_path, member_hash
        )
    session.flush()
    return new_patients, new_resources, resource_counts


def import_synthea_sample(
    session: Session,
    archive: Path,
    dataset_name: str,
    patient_limit: int,
    unsafe_override: bool = False,
) -> IngestionSummary:
    validate_patient_limit(patient_limit, unsafe_override)
    if not archive.is_file() or archive.suffixes[-2:] != [".tar", ".gz"]:
        raise ValueError("archive must be an existing .tar.gz file")
    started = datetime.now(UTC)
    archive_name = os.path.basename(archive)
    dataset = session.scalar(select(Dataset).where(Dataset.name == dataset_name))
    if dataset is None:
        dataset = Dataset(
            id=str(uuid.uuid4()),
            name=dataset_name,
            source_archive_name=archive_name,
            source_archive_sha256=sha256_file(archive),
            source_format="Synthea FHIR JSON bundle",
            sample_policy=SAMPLE_POLICY,
            requested_patient_limit=patient_limit,
            status="running",
            started_at=started,
        )
        session.add(dataset)
        session.flush()
    else:
        dataset.status = "running"
        dataset.requested_patient_limit = patient_limit
        dataset.started_at = started
    run = IngestionRun(
        id=str(uuid.uuid4()),
        dataset_id=dataset.id,
        status="running",
        archive_path_hash=archive_path_hash(archive),
        requested_limit=patient_limit,
        started_at=started,
    )
    session.add(run)
    session.flush()
    processed = imported_patients = imported_resources = skipped = errors = 0
    counts: dict[str, int] = {}
    try:
        for member_path, raw_bytes, bundle in selected_bundles(archive, patient_limit):
            processed += 1
            if dataset.synthea_version is None:
                dataset.synthea_version = synthea_version(resource_entries(bundle))
            try:
                with session.begin_nested():
                    new_patients, new_resources, bundle_counts = import_bundle(
                        session, dataset.id, archive_name, member_path, raw_bytes, bundle
                    )
                imported_patients += new_patients
                imported_resources += new_resources
                for resource_type, count in bundle_counts.items():
                    counts[resource_type] = counts.get(resource_type, 0) + count
                skipped += sum(
                    1
                    for resource in resource_entries(bundle)
                    if resource.get("resourceType") not in SUPPORTED_RESOURCE_TYPES
                )
                print(f"processed bundle {processed}/{patient_limit}: {member_path}")
            except Exception:
                errors += 1
        run.status = "completed"
        dataset.status = "completed"
    except Exception as exc:
        run.status = "failed"
        dataset.status = "failed"
        run.failure_message = str(exc)
        raise
    finished = datetime.now(UTC)
    dataset.imported_patient_count = (
        session.scalar(
            select(func.count()).select_from(Patient).where(Patient.dataset_id == dataset.id)
        )
        or 0
    )
    dataset.completed_at = finished
    run.processed_bundle_count = processed
    run.imported_patient_count = imported_patients
    run.imported_resource_count = imported_resources
    run.skipped_resource_count = skipped
    run.error_count = errors
    run.completed_at = finished
    session.commit()
    return IngestionSummary(
        dataset.id,
        run.id,
        run.status,
        processed,
        imported_patients,
        imported_resources,
        skipped,
        errors,
        counts,
    )
