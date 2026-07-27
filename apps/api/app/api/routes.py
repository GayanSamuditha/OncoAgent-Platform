import json
import time
from pathlib import Path
from typing import Any

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
from app.retrieval.model_registry import get_reranker, provider_for
from app.retrieval.search import hybrid_search, last_indexing, postgres_fts_search, search
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


def _evaluation_output() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[4]
    for filename in ("evaluation_outputs/phase2_6_results.json", "evaluation_outputs/phase2_5_results.json"):
        path = root / filename
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return {"status": "not_available", "profiles": {}}


@router.get("/api/v1/evaluations")
def evaluations() -> dict[str, object]:
    output = _evaluation_output()
    return {"items": [{"evaluation_id": "phase2-6-bounded", "dataset_id": output.get("dataset_id"), "status": output.get("status", "completed"), "synthetic_development_evaluation": True, "not_clinically_validated": True}] if output.get("profiles") else [], "notice": "Synthetic development evaluation; not clinically validated or production performance."}


@router.get("/api/v1/evaluations/{evaluation_id}")
def evaluation(evaluation_id: str) -> dict[str, object]:
    if evaluation_id not in {"phase2-5-bounded", "phase2-6-bounded"}:
        raise HTTPException(status_code=404, detail="evaluation not found")
    return _evaluation_output()


@router.get("/api/v1/evaluations/{evaluation_id}/profiles")
def evaluation_profiles(evaluation_id: str) -> dict[str, object]:
    if evaluation_id not in {"phase2-5-bounded", "phase2-6-bounded"}:
        raise HTTPException(status_code=404, detail="evaluation not found")
    output = _evaluation_output()
    return {"profiles": {name: value.get("metrics", {}) for name, value in output.get("profiles", {}).items()}, "notice": "Synthetic development evaluation; not clinically validated."}


@router.get("/api/v1/evaluations/{evaluation_id}/cases")
def evaluation_cases(evaluation_id: str, category: str | None = None) -> dict[str, object]:
    if evaluation_id not in {"phase2-5-bounded", "phase2-6-bounded"}:
        raise HTTPException(status_code=404, detail="evaluation not found")
    output = _evaluation_output()
    cases = [case for profile in output.get("profiles", {}).values() for case in profile.get("cases", [])]
    if category:
        cases = [case for case in cases if case.get("category") == category]
    return {"cases": cases, "notice": "Case-level results are synthetic development evaluation only."}


@router.get("/api/v1/retrieval-policy")
def retrieval_policy() -> dict[str, object]:
    path = Path(__file__).resolve().parents[4] / "evaluations/retrieval/retrieval_policy.json"
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/api/v1/clinical-search", response_model=ClinicalSearchResponse)
def clinical_search(request: ClinicalSearchRequest, session: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> ClinicalSearchResponse:
    if any(item not in {"encounter", "patient-summary"} for item in request.document_types):
        raise HTTPException(status_code=422, detail="unsupported document type")
    if request.candidate_pool_size < request.top_k:
        raise HTTPException(status_code=422, detail="candidate_pool_size must be greater than or equal to top_k")
    started = time.perf_counter()
    rerank_started = started
    metadata: dict[str, Any]
    reranker_metadata: dict[str, Any]
    try:
        dense_profile = request.retrieval_profile.replace("hybrid_", "")
        if request.retrieval_profile == "postgres_fts":
            items, first_latency = postgres_fts_search(session, request.dataset_id, request.query, request.candidate_pool_size, request.document_types, request.patient_id)
            metadata = {"query_model_name": "none", "query_model_revision": "none", "document_model_name": "postgresql-fts", "document_model_revision": "database", "representation_strategy": "lexical clinical document text", "normalization_strategy": "none", "lexical_provider": "postgres_fts", "dense_provider": None, "fusion_method": None, "rrf_constant": None}
        else:
            provider = provider_for(settings, dense_profile)
            provider.load()
            if request.retrieval_profile.startswith("hybrid_"):
                items, first_latency = hybrid_search(session, provider, request.dataset_id, request.query, request.candidate_pool_size, request.document_types, request.patient_id, settings.rrf_constant)
                metadata = {"query_model_name": provider.metadata.query_model_name, "query_model_revision": provider.metadata.query_model_revision, "document_model_name": provider.metadata.document_model_name, "document_model_revision": provider.metadata.document_model_revision, "representation_strategy": provider.metadata.pooling_strategy, "normalization_strategy": provider.metadata.normalization_strategy, "lexical_provider": "postgres_fts", "dense_provider": dense_profile, "fusion_method": "reciprocal_rank_fusion", "rrf_constant": settings.rrf_constant}
            else:
                items, first_latency = search(session, provider, request.dataset_id, request.query, request.candidate_pool_size, request.document_types, request.patient_id, request.minimum_score)
                metadata = {"query_model_name": provider.metadata.query_model_name, "query_model_revision": provider.metadata.query_model_revision, "document_model_name": provider.metadata.document_model_name, "document_model_revision": provider.metadata.document_model_revision, "representation_strategy": provider.metadata.pooling_strategy, "normalization_strategy": provider.metadata.normalization_strategy, "lexical_provider": None, "dense_provider": dense_profile, "fusion_method": None, "rrf_constant": None}
        if request.reranker == "medcpt_cross_encoder":
            reranker = get_reranker(settings.reranker_model, settings.reranker_model_revision, settings.embedding_device, settings.reranker_batch_size)
            reranker.load()
            logits = reranker.rerank(request.query, items)
            for item, logit in zip(items, logits, strict=True):
                item["reranker_logit"] = logit
            items = sorted(items, key=lambda item: (-float(item["reranker_logit"]), str(item["document_id"])))  # type: ignore[arg-type]
            for index, item in enumerate(items, 1):
                item["initial_candidate_rank"] = item.get("initial_candidate_rank", item.get("rank", index))
                item["reranked_rank"] = index
                item["final_rank"] = index
            reranker_metadata = {"reranker_model_name": reranker.metadata.model_name, "reranker_model_revision": reranker.metadata.model_revision}
        else:
            reranker_metadata = {"reranker_model_name": None, "reranker_model_revision": None}
        items = items[:request.top_k]
        for index, item in enumerate(items, 1):
            item["rank"] = index
            item["final_rank"] = index
        reranking_latency = (time.perf_counter() - rerank_started) * 1000 - first_latency
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503 if isinstance(exc, RuntimeError) else 422, detail=str(exc)) from exc
    return ClinicalSearchResponse(query=request.query, dataset_id=request.dataset_id, result_count=len(items), model_name=metadata["document_model_name"], model_revision=metadata["document_model_revision"], search_latency_ms=(time.perf_counter() - started) * 1000, synthetic_data_notice="Synthetic Synthea data only.", score_notice="All retrieval and reranking scores are ranking signals, not clinical probabilities.", retrieval_profile=request.retrieval_profile, **metadata, reranker=request.reranker, candidate_pool_size=request.candidate_pool_size, first_stage_latency_ms=first_latency, reranking_latency_ms=max(0, reranking_latency), total_latency_ms=(time.perf_counter() - started) * 1000, **reranker_metadata, items=[ClinicalSearchResult.model_validate(item) for item in items])


@router.get("/api/v1/models/clinical-embedding", response_model=ModelStatusResponse)
def clinical_embedding_status(settings: Settings = Depends(get_settings), session: Session = Depends(get_db)) -> ModelStatusResponse:
    statuses: dict[str, object] = {"postgres_fts": {"configured": True, "loaded": True, "available": True, "device": "database", "limitations": ["Lexical baseline only."]}}
    for profile in ("medcpt", "bioclinicalbert"):
        provider = provider_for(settings, profile)
        statuses[profile] = provider.health()
    statuses["medcpt_cross_encoder"] = get_reranker(settings.reranker_model, settings.reranker_model_revision, settings.embedding_device, settings.reranker_batch_size).health()
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
