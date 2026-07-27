import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.ingestion import (
    Condition,
    DiagnosticReport,
    Encounter,
    ImagingStudy,
    MedicationRequest,
    Observation,
    Patient,
    Procedure,
)
from app.models.retrieval import ClinicalDocument, ClinicalDocumentChunk

BUILDER_VERSION = "clinical-doc-builder-v1"
DOCUMENT_VERSION = "phase2-v1"


def _date(value: datetime | None) -> str:
    return value.isoformat() if value else "unknown"


def _fact(label: str, display: str | None, code: str | None, system: str | None, value: str = "") -> str:
    text = display or code or "unspecified"
    suffix = f" ({system} {code})" if code and system else ""
    return f"- {label}: {text}{suffix}{value}"


@dataclass(frozen=True)
class BuiltDocument:
    patient_id: str
    encounter_id: str | None
    document_type: str
    text: str
    title: str
    source_resource_ids: list[str]


def build_encounter_document(session: Session, patient: Patient, encounter: Encounter) -> BuiltDocument:
    lines = [f"Encounter date: {_date(encounter.start_time)}", f"Encounter type: {encounter.encounter_type_display or encounter.encounter_class or 'unknown'}"]
    ids = [encounter.source_resource_id]
    sections: list[tuple[str, list[str]]] = [("Conditions", []), ("Observations", []), ("Procedures", []), ("Medication requests", []), ("Diagnostic reports", []), ("Imaging studies", [])]
    rows: list[tuple[str, Any]] = [
        ("Conditions", session.scalars(select(Condition).where(Condition.encounter_id == encounter.id)).all()),
        ("Observations", session.scalars(select(Observation).where(Observation.encounter_id == encounter.id)).all()),
        ("Procedures", session.scalars(select(Procedure).where(Procedure.encounter_id == encounter.id)).all()),
        ("Medication requests", session.scalars(select(MedicationRequest).where(MedicationRequest.encounter_id == encounter.id)).all()),
        ("Diagnostic reports", session.scalars(select(DiagnosticReport).where(DiagnosticReport.encounter_id == encounter.id)).all()),
        ("Imaging studies", session.scalars(select(ImagingStudy).where(ImagingStudy.encounter_id == encounter.id)).all()),
    ]
    for title, values in rows:
        target = dict(sections)[title]
        for row in sorted(values, key=lambda item: ((getattr(item, "display", None) or ""), item.fhir_id)):
            if isinstance(row, Observation):
                value = f": {row.value_numeric} {row.unit or ''}" if row.value_numeric is not None else (f": {row.value_text}" if row.value_text else "")
                target.append(_fact("observation", row.display, row.code, row.code_system, value))
            elif isinstance(row, ImagingStudy):
                target.append(f"- imaging: {row.description or 'unspecified'}")
            else:
                target.append(_fact(title[:-1].lower(), row.display, row.code, row.code_system))
            ids.append(row.source_resource_id)
    for title, values in sections:
        if values:
            lines.extend(["", f"{title}:", *values])
    title = f"{encounter.encounter_type_display or encounter.encounter_class or 'Unknown'} encounter on {_date(encounter.start_time)[:10]}"
    return BuiltDocument(str(patient.id), str(encounter.id), "encounter", "\n".join(lines), title, sorted(set(ids)))


def persist_document(session: Session, built: BuiltDocument, token_count: int) -> ClinicalDocument:
    digest = hashlib.sha256(built.text.encode()).hexdigest()
    existing = session.scalar(select(ClinicalDocument).where(ClinicalDocument.dataset_id == _dataset_id(session, built.patient_id), ClinicalDocument.patient_id == built.patient_id, ClinicalDocument.encounter_id == built.encounter_id, ClinicalDocument.document_type == built.document_type, ClinicalDocument.document_version == DOCUMENT_VERSION))
    title_digest = hashlib.sha256(built.title.encode()).hexdigest()
    if existing is not None and existing.text_sha256 == digest and existing.title_sha256 == title_digest and existing.source_resource_ids == built.source_resource_ids:
        return existing
    if existing is None:
        existing = ClinicalDocument(id=str(uuid4()), dataset_id=_dataset_id(session, built.patient_id), patient_id=built.patient_id, encounter_id=built.encounter_id, document_type=built.document_type, document_version=DOCUMENT_VERSION, text=built.text, title=built.title, title_sha256=title_digest, body_sha256=digest, text_sha256=digest, token_count=token_count, source_resource_ids=built.source_resource_ids, source_resource_count=len(built.source_resource_ids), builder_version=BUILDER_VERSION)
        session.add(existing)
    else:
        session.execute(delete(ClinicalDocumentChunk).where(ClinicalDocumentChunk.document_id == existing.id))
        existing.text, existing.title = built.text, built.title
        existing.text_sha256, existing.body_sha256, existing.title_sha256, existing.token_count = digest, digest, title_digest, token_count
        existing.source_resource_ids, existing.source_resource_count = built.source_resource_ids, len(built.source_resource_ids)
    return existing


def _dataset_id(session: Session, patient_id: str) -> str:
    return str(session.scalar(select(Patient.dataset_id).where(Patient.id == patient_id)))


def build_documents(session: Session, dataset_id: str, document_type: str = "encounter", limit: int | None = None, tokenizer: object | None = None) -> int:
    if document_type != "encounter":
        raise ValueError("patient-summary generation is reserved for the bounded summary implementation")
    query = select(Patient, Encounter).join(Encounter, Encounter.patient_id == Patient.id).where(Patient.dataset_id == dataset_id).order_by(Patient.fhir_id, Encounter.start_time, Encounter.fhir_id)
    count = 0
    for patient, encounter in session.execute(query).yield_per(50):
        built = build_encounter_document(session, patient, encounter)
        token_count = len(cast(Any, tokenizer).encode(built.text, add_special_tokens=False)) if tokenizer else len(built.text.split())
        persist_document(session, built, token_count)
        count += 1
        if limit is not None and count >= limit:
            break
        if count % 50 == 0:
            session.commit()
    session.commit()
    return count
