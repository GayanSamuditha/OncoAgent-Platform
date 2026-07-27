from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ingestion import (
    Condition,
    DiagnosticReport,
    Encounter,
    ImagingStudy,
    MedicationRequest,
    Observation,
    Procedure,
)
from app.schemas.ingestion import TimelineEvent


def timeline(session: Session, patient_id: str) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    encounter_rows = list(
        session.scalars(select(Encounter).where(Encounter.patient_id == patient_id))
    )
    encounter_references = {row.id: row.fhir_id for row in encounter_rows}
    for row in encounter_rows:
        events.append(
            TimelineEvent(
                event_type="Encounter",
                timestamp=row.start_time,
                clinical_display=row.encounter_type_display,
                code=row.encounter_type_code,
                code_system=None,
                encounter_reference=row.fhir_id,
                source_fhir_resource_id=row.source_resource_id,
            )
        )
    models: list[tuple[Any, str]] = [
        (Condition, "Condition"),
        (Observation, "Observation"),
        (Procedure, "Procedure"),
        (MedicationRequest, "MedicationRequest"),
        (DiagnosticReport, "DiagnosticReport"),
        (ImagingStudy, "ImagingStudy"),
    ]
    for model, event_type in models:
        for row in session.scalars(select(model).where(model.patient_id == patient_id)):
            if event_type == "Condition":
                timestamp, display, code, system, encounter = (
                    row.onset_time,
                    row.display,
                    row.code,
                    row.code_system,
                    row.encounter_id,
                )
            elif event_type == "Observation":
                timestamp, display, code, system, encounter = (
                    row.effective_time,
                    row.display or row.value_text,
                    row.code,
                    row.code_system,
                    row.encounter_id,
                )
            elif event_type == "Procedure":
                timestamp, display, code, system, encounter = (
                    row.performed_start,
                    row.display,
                    row.code,
                    row.code_system,
                    row.encounter_id,
                )
            elif event_type == "MedicationRequest":
                timestamp, display, code, system, encounter = (
                    row.authored_on,
                    row.display,
                    row.code,
                    row.code_system,
                    row.encounter_id,
                )
            elif event_type == "DiagnosticReport":
                timestamp, display, code, system, encounter = (
                    row.effective_time,
                    row.display,
                    row.code,
                    row.code_system,
                    row.encounter_id,
                )
            else:
                timestamp, display, code, system, encounter = (
                    row.started_at,
                    row.description,
                    None,
                    None,
                    row.encounter_id,
                )
            events.append(
                TimelineEvent(
                    event_type=event_type,
                    timestamp=timestamp,
                    clinical_display=display,
                    code=code,
                    code_system=system,
                    encounter_reference=encounter_references.get(encounter),
                    source_fhir_resource_id=row.source_resource_id,
                )
            )
    return sorted(events, key=lambda event: (event.timestamp is None, event.timestamp))
