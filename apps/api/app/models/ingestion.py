from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    source_archive_name: Mapped[str] = mapped_column(String(512), nullable=False)
    source_archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_format: Mapped[str] = mapped_column(String(50), nullable=False)
    synthea_version: Mapped[str | None] = mapped_column(String(300))
    sample_policy: Mapped[str] = mapped_column(Text, nullable=False)
    requested_patient_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_patient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    archive_path_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    processed_bundle_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_patient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_resource_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_resource_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_message: Mapped[str | None] = mapped_column(Text)


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (UniqueConstraint("dataset_id", "fhir_id", name="uq_patients_dataset_fhir"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    fhir_id: Mapped[str] = mapped_column(String(200), nullable=False)
    birth_date: Mapped[str | None] = mapped_column(String(50))
    gender: Mapped[str | None] = mapped_column(String(50))
    deceased: Mapped[bool | None] = mapped_column()
    source_resource_id: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Encounter(Base):
    __tablename__ = "encounters"
    __table_args__ = (UniqueConstraint("dataset_id", "fhir_id", name="uq_encounters_dataset_fhir"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    fhir_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str | None] = mapped_column(String(50))
    encounter_class: Mapped[str | None] = mapped_column(String(100))
    encounter_type_code: Mapped[str | None] = mapped_column(String(200))
    encounter_type_display: Mapped[str | None] = mapped_column(Text)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_resource_id: Mapped[str] = mapped_column(String(200), nullable=False)


class Condition(Base):
    __tablename__ = "conditions"
    __table_args__ = (UniqueConstraint("dataset_id", "fhir_id", name="uq_conditions_dataset_fhir"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    encounter_id: Mapped[str | None] = mapped_column(ForeignKey("encounters.id"))
    fhir_id: Mapped[str] = mapped_column(String(200), nullable=False)
    clinical_status: Mapped[str | None] = mapped_column(String(100))
    verification_status: Mapped[str | None] = mapped_column(String(100))
    code_system: Mapped[str | None] = mapped_column(String(500))
    code: Mapped[str | None] = mapped_column(String(200))
    display: Mapped[str | None] = mapped_column(Text)
    onset_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    abatement_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_resource_id: Mapped[str] = mapped_column(String(200), nullable=False)


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("dataset_id", "fhir_id", name="uq_observations_dataset_fhir"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    encounter_id: Mapped[str | None] = mapped_column(ForeignKey("encounters.id"))
    fhir_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str | None] = mapped_column(String(50))
    category: Mapped[str | None] = mapped_column(Text)
    code_system: Mapped[str | None] = mapped_column(String(500))
    code: Mapped[str | None] = mapped_column(String(200))
    display: Mapped[str | None] = mapped_column(Text)
    value_numeric: Mapped[float | None] = mapped_column()
    value_text: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(100))
    effective_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_resource_id: Mapped[str] = mapped_column(String(200), nullable=False)


class Procedure(Base):
    __tablename__ = "procedures"
    __table_args__ = (UniqueConstraint("dataset_id", "fhir_id", name="uq_procedures_dataset_fhir"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    encounter_id: Mapped[str | None] = mapped_column(ForeignKey("encounters.id"))
    fhir_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str | None] = mapped_column(String(50))
    code_system: Mapped[str | None] = mapped_column(String(500))
    code: Mapped[str | None] = mapped_column(String(200))
    display: Mapped[str | None] = mapped_column(Text)
    performed_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    performed_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_resource_id: Mapped[str] = mapped_column(String(200), nullable=False)


class MedicationRequest(Base):
    __tablename__ = "medication_requests"
    __table_args__ = (
        UniqueConstraint("dataset_id", "fhir_id", name="uq_medication_requests_dataset_fhir"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    encounter_id: Mapped[str | None] = mapped_column(ForeignKey("encounters.id"))
    fhir_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str | None] = mapped_column(String(50))
    intent: Mapped[str | None] = mapped_column(String(50))
    code_system: Mapped[str | None] = mapped_column(String(500))
    code: Mapped[str | None] = mapped_column(String(200))
    display: Mapped[str | None] = mapped_column(Text)
    authored_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_resource_id: Mapped[str] = mapped_column(String(200), nullable=False)


class DiagnosticReport(Base):
    __tablename__ = "diagnostic_reports"
    __table_args__ = (
        UniqueConstraint("dataset_id", "fhir_id", name="uq_diagnostic_reports_dataset_fhir"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    encounter_id: Mapped[str | None] = mapped_column(ForeignKey("encounters.id"))
    fhir_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str | None] = mapped_column(String(50))
    code_system: Mapped[str | None] = mapped_column(String(500))
    code: Mapped[str | None] = mapped_column(String(200))
    display: Mapped[str | None] = mapped_column(Text)
    effective_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_resource_id: Mapped[str] = mapped_column(String(200), nullable=False)


class ImagingStudy(Base):
    __tablename__ = "imaging_studies"
    __table_args__ = (
        UniqueConstraint("dataset_id", "fhir_id", name="uq_imaging_studies_dataset_fhir"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    encounter_id: Mapped[str | None] = mapped_column(ForeignKey("encounters.id"))
    fhir_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str | None] = mapped_column(String(50))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    modality_codes: Mapped[list[Any] | None] = mapped_column(JSONB)
    description: Mapped[str | None] = mapped_column(Text)
    source_resource_id: Mapped[str] = mapped_column(String(200), nullable=False)


class FhirResource(Base):
    __tablename__ = "fhir_resources"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id", "resource_type", "fhir_id", name="uq_fhir_resources_identity"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("patients.id"), index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    fhir_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_archive_name: Mapped[str] = mapped_column(String(512), nullable=False)
    source_member_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_member_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_resource_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
