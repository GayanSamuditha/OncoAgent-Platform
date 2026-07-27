from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.ingestion import FhirResource
from app.models.retrieval import ClinicalDocument, ClinicalDocumentChunk, IndexingRun
from app.repositories.ingestion import (
    get_dataset,
    get_ingestion_run,
    get_patient,
    list_datasets,
    list_ingestion_runs,
    list_patients,
    patient_count,
)
from app.retrieval.model_registry import provider_for
from app.retrieval.search import last_indexing, postgres_fts_search, search
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
from app.schemas.retrieval import (
    ClinicalSearchRequest,
    ClinicalSearchResponse,
    ClinicalSearchResult,
    ModelStatusResponse,
)
from app.services.health import database_is_available
from app.services.timeline import timeline

router = APIRouter()


@router.post("/api/v1/clinical-search", response_model=ClinicalSearchResponse)
def clinical_search(request: ClinicalSearchRequest, session: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> ClinicalSearchResponse:
    if any(item not in {"encounter", "patient-summary"} for item in request.document_types):
        raise HTTPException(status_code=422, detail="unsupported document type")
    try:
        if request.retrieval_profile == "postgres_fts":
            items, latency = postgres_fts_search(session, request.dataset_id, request.query, request.top_k, request.document_types, request.patient_id)
            metadata = {"query_model_name": "none", "query_model_revision": "none", "document_model_name": "postgresql-fts", "document_model_revision": "database", "representation_strategy": "lexical clinical document text", "normalization_strategy": "none"}
        else:
            provider = provider_for(settings, request.retrieval_profile)
            provider.load()  # type: ignore[attr-defined]
            items, latency = search(session, provider, request.dataset_id, request.query, request.top_k, request.document_types, request.patient_id, request.minimum_score)
            metadata = {"query_model_name": provider.metadata.query_model_name, "query_model_revision": provider.metadata.query_model_revision, "document_model_name": provider.metadata.document_model_name, "document_model_revision": provider.metadata.document_model_revision, "representation_strategy": provider.metadata.pooling_strategy, "normalization_strategy": provider.metadata.normalization_strategy}
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503 if isinstance(exc, RuntimeError) else 422, detail=str(exc)) from exc
    return ClinicalSearchResponse(query=request.query, dataset_id=request.dataset_id, result_count=len(items), model_name=metadata["document_model_name"], model_revision=metadata["document_model_revision"], search_latency_ms=latency, synthetic_data_notice="Synthetic Synthea data only.", score_notice="Retrieval scores are ranking signals, not clinical probabilities.", retrieval_profile=request.retrieval_profile, **metadata, items=[ClinicalSearchResult.model_validate(item) for item in items])


@router.get("/api/v1/models/clinical-embedding", response_model=ModelStatusResponse)
def clinical_embedding_status(settings: Settings = Depends(get_settings), session: Session = Depends(get_db)) -> ModelStatusResponse:
    statuses: dict[str, object] = {"postgres_fts": {"configured": True, "loaded": True, "available": True, "device": "database", "limitations": ["Lexical baseline only."]}}
    for profile in ("medcpt", "bioclinicalbert"):
        provider = provider_for(settings, profile)
        statuses[profile] = provider.health()
    medcpt = provider_for(settings, "medcpt")
    last = last_indexing(session, medcpt.metadata.document_model_name)
    return ModelStatusResponse(providers=statuses, configured_model=medcpt.metadata.document_model_name, loaded_status="loaded" if medcpt.health()["loaded"] else "not_loaded", device=medcpt.metadata.device, embedding_dimension=medcpt.metadata.embedding_dimension, maximum_sequence_length=medcpt.metadata.document_max_length, pooling_method=medcpt.metadata.pooling_strategy, revision=medcpt.metadata.document_model_revision, last_successful_indexing_time=last.completed_at if last else None, current_limitations=["Synthetic data only.", "Retrieval is not clinical validation.", "MedCPT was trained for PubMed-like biomedical text and may not generalize to all synthetic FHIR phrasing."])


@router.get("/api/v1/indexing-runs")
def retrieval_indexing_runs(session: Session = Depends(get_db)) -> list[dict[str, object]]:
    return [{key: getattr(item, key) for key in ("id", "dataset_id", "model_name", "model_revision", "status", "requested_document_count", "processed_document_count", "created_embedding_count", "skipped_embedding_count", "failed_embedding_count", "batch_size", "device_type", "started_at", "completed_at", "failure_message")} for item in session.scalars(select(IndexingRun).order_by(IndexingRun.started_at.desc())).all()]


@router.get("/api/v1/indexing-runs/{run_id}")
def retrieval_indexing_run(run_id: str, session: Session = Depends(get_db)) -> dict[str, object]:
    item = session.get(IndexingRun, run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="indexing run not found")
    return {key: getattr(item, key) for key in ("id", "dataset_id", "model_name", "model_revision", "status", "requested_document_count", "processed_document_count", "created_embedding_count", "skipped_embedding_count", "failed_embedding_count", "batch_size", "device_type", "started_at", "completed_at", "failure_message", "configuration")}


@router.get("/api/v1/clinical-documents/{document_id}/provenance")
def clinical_document_provenance(document_id: str, session: Session = Depends(get_db)) -> dict[str, object]:
    document = session.get(ClinicalDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="clinical document not found")
    chunks = session.scalars(select(ClinicalDocumentChunk).where(ClinicalDocumentChunk.document_id == document_id).order_by(ClinicalDocumentChunk.chunk_index)).all()
    resources = session.scalars(select(FhirResource).where(FhirResource.dataset_id == document.dataset_id, FhirResource.fhir_id.in_(document.source_resource_ids))).all()
    return {"document": {"id": document.id, "dataset_id": document.dataset_id, "patient_id": document.patient_id, "encounter_id": document.encounter_id, "document_type": document.document_type, "document_version": document.document_version, "text_sha256": document.text_sha256, "builder_version": document.builder_version, "source_resource_ids": document.source_resource_ids}, "chunks": [{"id": c.id, "chunk_index": c.chunk_index, "token_start": c.token_start, "token_end": c.token_end, "token_count": c.token_count, "source_resource_ids": c.source_resource_ids} for c in chunks], "resources": [{"resource_type": r.resource_type, "fhir_id": r.fhir_id, "source_archive_name": r.source_archive_name, "source_member_path": r.source_member_path} for r in resources], "synthetic_data_notice": "Synthetic Synthea data only."}


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
