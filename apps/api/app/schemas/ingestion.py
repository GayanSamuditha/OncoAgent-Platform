from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class DatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    source_archive_name: str
    source_archive_sha256: str
    source_format: str
    synthea_version: str | None
    sample_policy: str
    requested_patient_limit: int
    imported_patient_count: int
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class IngestionRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    status: str
    requested_limit: int
    processed_bundle_count: int
    imported_patient_count: int
    imported_resource_count: int
    skipped_resource_count: int
    error_count: int
    started_at: datetime | None
    completed_at: datetime | None
    failure_message: str | None


class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    fhir_id: str
    birth_date: str | None
    gender: str | None
    deceased: bool | None
    source_resource_id: str
    created_at: datetime
    updated_at: datetime


class PageInfo(BaseModel):
    page: int
    page_size: int
    total: int


class PatientPage(BaseModel):
    items: list[PatientResponse]
    page: PageInfo


class TimelineEvent(BaseModel):
    event_type: str
    timestamp: datetime | None
    clinical_display: str | None
    code: str | None
    code_system: str | None
    encounter_reference: str | None
    source_fhir_resource_id: str
    synthetic_data_notice: Literal["Synthetic Synthea data only."] = "Synthetic Synthea data only."


class PatientTimelineResponse(BaseModel):
    patient_id: str
    dataset_id: str
    events: list[TimelineEvent]


class ImportSummaryResponse(BaseModel):
    dataset_id: str
    ingestion_run_id: str
    status: str
    processed_bundle_count: int
    imported_patient_count: int
    imported_resource_count: int
    skipped_resource_count: int
    error_count: int
    resource_counts: dict[str, int]
