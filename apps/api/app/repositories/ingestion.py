from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ingestion import Dataset, IngestionRun, Patient


def list_datasets(session: Session) -> list[Dataset]:
    return list(session.scalars(select(Dataset).order_by(Dataset.created_at.desc())))


def get_dataset(session: Session, dataset_id: str) -> Dataset | None:
    return session.get(Dataset, dataset_id)


def list_ingestion_runs(session: Session) -> list[IngestionRun]:
    return list(session.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc())))


def get_ingestion_run(session: Session, run_id: str) -> IngestionRun | None:
    return session.get(IngestionRun, run_id)


def patient_count(session: Session, dataset_id: str | None) -> int:
    statement = select(func.count()).select_from(Patient)
    if dataset_id:
        statement = statement.where(Patient.dataset_id == dataset_id)
    return int(session.scalar(statement) or 0)


def list_patients(
    session: Session, dataset_id: str | None, offset: int, limit: int
) -> list[Patient]:
    statement = select(Patient).order_by(Patient.fhir_id).offset(offset).limit(limit)
    if dataset_id:
        statement = statement.where(Patient.dataset_id == dataset_id)
    return list(session.scalars(statement))


def get_patient(session: Session, patient_id: str) -> Patient | None:
    return session.get(Patient, patient_id)
