from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.ingestion import (
    get_dataset,
    get_ingestion_run,
    get_patient,
    list_datasets,
    list_ingestion_runs,
    list_patients,
    patient_count,
)
from app.schemas.ingestion import (
    DatasetResponse,
    IngestionRunResponse,
    PageInfo,
    PatientPage,
    PatientResponse,
    PatientTimelineResponse,
)
from app.schemas.platform import (
    CapabilitySet,
    HealthResponse,
    PlatformInfoResponse,
    ReadinessResponse,
)
from app.services.health import database_is_available
from app.services.timeline import timeline

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name, version=settings.app_version)


@router.get("/ready", response_model=ReadinessResponse)
def ready(
    response: Response,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ReadinessResponse:
    database_available = database_is_available(session)
    if not database_available:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if database_available else "not_ready",
        service=settings.app_name,
        version=settings.app_version,
        database="available" if database_available else "unavailable",
    )


@router.get("/api/v1/platform/info", response_model=PlatformInfoResponse)
def platform_info(settings: Settings = Depends(get_settings)) -> PlatformInfoResponse:
    return PlatformInfoResponse(
        platform_name="OncoAgent Platform",
        application_version=settings.app_version,
        data_policy="Synthetic Synthea data only.",
        clinical_validation_status="Not clinically validated.",
        capabilities=CapabilitySet(
            implemented=["Platform health and readiness reporting", "Foundation metadata API"],
            planned=[
                "Bounded Synthea ingestion",
                "BioClinicalBERT retrieval",
                "LangGraph governed workflows",
                "Human approval workflows",
                "MCP and CrewAI interoperability",
                "Temporal and Ray execution",
                "Kubernetes and controlled releases",
            ],
        ),
    )


@router.get("/api/v1/datasets", response_model=list[DatasetResponse])
def datasets(session: Session = Depends(get_db)) -> list[DatasetResponse]:
    return [DatasetResponse.model_validate(item) for item in list_datasets(session)]


@router.get("/api/v1/datasets/{dataset_id}", response_model=DatasetResponse)
def dataset(dataset_id: str, session: Session = Depends(get_db)) -> DatasetResponse:
    item = get_dataset(session, dataset_id)
    if item is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return DatasetResponse.model_validate(item)


@router.get("/api/v1/ingestion-runs", response_model=list[IngestionRunResponse])
def ingestion_runs(session: Session = Depends(get_db)) -> list[IngestionRunResponse]:
    return [IngestionRunResponse.model_validate(item) for item in list_ingestion_runs(session)]


@router.get("/api/v1/ingestion-runs/{run_id}", response_model=IngestionRunResponse)
def ingestion_run(run_id: str, session: Session = Depends(get_db)) -> IngestionRunResponse:
    item = get_ingestion_run(session, run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="ingestion run not found")
    return IngestionRunResponse.model_validate(item)


@router.get("/api/v1/patients", response_model=PatientPage)
def patients(
    dataset_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_db),
) -> PatientPage:
    total = patient_count(session, dataset_id)
    rows = list_patients(session, dataset_id, (page - 1) * page_size, page_size)
    return PatientPage(
        items=[PatientResponse.model_validate(item) for item in rows],
        page=PageInfo(page=page, page_size=page_size, total=total),
    )


@router.get("/api/v1/patients/{patient_id}", response_model=PatientResponse)
def patient(patient_id: str, session: Session = Depends(get_db)) -> PatientResponse:
    item = get_patient(session, patient_id)
    if item is None:
        raise HTTPException(status_code=404, detail="patient not found")
    return PatientResponse.model_validate(item)


@router.get("/api/v1/patients/{patient_id}/timeline", response_model=PatientTimelineResponse)
def patient_timeline(
    patient_id: str, session: Session = Depends(get_db)
) -> PatientTimelineResponse:
    item = get_patient(session, patient_id)
    if item is None:
        raise HTTPException(status_code=404, detail="patient not found")
    return PatientTimelineResponse(
        patient_id=item.id, dataset_id=item.dataset_id, events=timeline(session, item.id)
    )
