import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal, get_db
from app.mcp_identity import configured_clients
from app.models.ingestion import FhirResource
from app.models.mcp import MCPRequest
from app.models.retrieval import ClinicalDocument, ClinicalDocumentChunk, IndexingRun
from app.models.workflow import ApprovalRequest, WorkflowEvent, WorkflowRun
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
from app.workflow.audit import existing_decision
from app.workflow.planner import (
    PLANNING_SYSTEM_PROMPT,
    OllamaQwenPlannerProvider,
    allowed_local_planner_models,
)
from app.workflow.policy_selection import select_policy
from app.workflow.schemas import (
    ActorContext,
    ApprovalDecisionRequest,
    Criterion,
    RunCreateRequest,
    RunResponse,
)
from app.workflow.service import (
    create_run,
    get_approval_request,
    get_run,
    list_candidates,
    list_events,
    list_evidence,
    resume_run,
)
from app.workflow.tools import build_tool_registry

router = APIRouter()


def development_actor(x_actor_id: str | None = Header(default=None), x_actor_role: str | None = Header(default=None)) -> ActorContext:
    if not x_actor_id or x_actor_role not in {"researcher", "reviewer", "admin"}:
        raise HTTPException(status_code=401, detail="X-Actor-Id and X-Actor-Role are required development identity headers")
    return ActorContext(actor_id=x_actor_id, role=x_actor_role)  # type: ignore[arg-type]


def _run_response(run: WorkflowRun) -> RunResponse:
    return RunResponse(run_id=run.id, thread_id=run.thread_id, status=run.status, current_node=run.current_node, created_at=run.created_at, dataset_id=run.dataset_id, actor_id=run.actor_id, actor_role=run.actor_role, approval_id=run.approval_id, structured_plan=run.structured_plan, planner_lineage=run.planner_lineage, final_result=run.final_result, warnings=run.warnings, errors=run.errors, links={"self": f"/api/v1/runs/{run.id}", "events": f"/api/v1/runs/{run.id}/events", "evidence": f"/api/v1/runs/{run.id}/evidence", "candidates": f"/api/v1/runs/{run.id}/candidates"})


def _safe_model(item: Any) -> dict[str, Any]:
    return {key: (value.isoformat() if hasattr(value, "isoformat") else value) for key, value in item.__dict__.items() if not key.startswith("_")}


@router.post("/api/v1/runs", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
def create_workflow_run(request: RunCreateRequest, actor: ActorContext = Depends(development_actor), settings: Settings = Depends(get_settings)) -> RunResponse:
    try:
        return _run_response(create_run(request, actor, settings))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/api/v1/runs")
def list_workflow_runs(page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100), dataset_id: str | None = None, _: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    with SessionLocal() as session:
        statement = select(WorkflowRun).order_by(WorkflowRun.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        if dataset_id:
            statement = statement.where(WorkflowRun.dataset_id == dataset_id)
        items = [_safe_model(item) for item in session.scalars(statement)]
    return {"items": items, "page": page, "page_size": page_size}


@router.get("/api/v1/runs/{run_id}/events")
def workflow_events(run_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=100, ge=1, le=200), _: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    if get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="workflow run not found")
    items = list_events(run_id)
    start = (page - 1) * page_size
    return {"items": [_safe_model(item) for item in items[start:start + page_size]], "page": page, "page_size": page_size}


@router.get("/api/v1/runs/{run_id}/evidence")
def workflow_evidence(run_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=100, ge=1, le=200), _: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    if get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="workflow run not found")
    items = list_evidence(run_id)
    start = (page - 1) * page_size
    return {"items": [_safe_model(item) for item in items[start:start + page_size]], "page": page, "page_size": page_size}


@router.get("/api/v1/runs/{run_id}/candidates")
def workflow_candidates(run_id: str, page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100), _: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    if get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="workflow run not found")
    items = list_candidates(run_id)
    start = (page - 1) * page_size
    return {"items": [_safe_model(item) for item in items[start:start + page_size]], "page": page, "page_size": page_size}


@router.get("/api/v1/runs/{run_id}/stream")
def workflow_stream(run_id: str, _: ActorContext = Depends(development_actor)) -> StreamingResponse:
    if get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="workflow run not found")
    def stream() -> Any:
        for item in list_events(run_id):
            yield f"event: {item.event_type}\ndata: {json.dumps(_safe_model(item), default=str)}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/api/v1/runs/{run_id}", response_model=RunResponse)
def workflow_run(run_id: str, _: ActorContext = Depends(development_actor)) -> RunResponse:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="workflow run not found")
    return _run_response(run)


@router.post("/api/v1/runs/{run_id}/cancel", response_model=RunResponse)
def cancel_workflow_run(run_id: str, actor: ActorContext = Depends(development_actor), settings: Settings = Depends(get_settings)) -> RunResponse:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="workflow run not found")
    if run.status in {"completed", "rejected", "cancelled", "failed", "needs_clarification"}:
        raise HTTPException(status_code=409, detail="terminal workflow runs cannot be cancelled")
    if actor.role == "researcher" and actor.actor_id != run.actor_id:
        raise HTTPException(status_code=403, detail="researchers may cancel only their own runs")
    if not run.approval_id:
        raise HTTPException(status_code=409, detail="run is not at a cancellable checkpoint")
    try:
        return _run_response(resume_run(run, {"decision": "cancel", "actor_id": actor.actor_id, "actor_role": actor.role, "comment": "Cancelled by actor."}, settings))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/api/v1/approvals")
def approvals(page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100), _: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    with SessionLocal() as session:
        items = list(session.scalars(select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc()).offset((page - 1) * page_size).limit(page_size)))
    return {"items": [_safe_model(item) for item in items], "page": page, "page_size": page_size}


@router.get("/api/v1/approvals/{approval_id}")
def approval(approval_id: str, _: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    item = get_approval_request(approval_id)
    if item is None:
        raise HTTPException(status_code=404, detail="approval request not found")
    return _safe_model(item)


@router.post("/api/v1/approvals/{approval_id}/decision", response_model=RunResponse)
def approval_decision(approval_id: str, request: ApprovalDecisionRequest, actor: ActorContext = Depends(development_actor), settings: Settings = Depends(get_settings)) -> RunResponse:
    approval_item = get_approval_request(approval_id)
    if approval_item is None:
        raise HTTPException(status_code=404, detail="approval request not found")
    run = get_run(approval_item.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="workflow run not found")
    if run.status in {"completed", "rejected", "cancelled", "failed", "needs_clarification"}:
        raise HTTPException(status_code=409, detail="workflow run is terminal")
    if existing_decision(approval_id) is not None:
        raise HTTPException(status_code=409, detail="approval already has a decision")
    if request.decision in {"approve", "reject", "request_changes"} and actor.role not in {"reviewer", "admin"}:
        raise HTTPException(status_code=403, detail="only reviewers or admins may decide approval")
    if request.decision == "approve" and actor.actor_id == run.actor_id:
        raise HTTPException(status_code=403, detail="researcher and reviewer must be different actors")
    try:
        return _run_response(resume_run(run, {"decision": request.decision, "actor_id": actor.actor_id, "actor_role": actor.role, "comment": request.comment}, settings))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/api/v1/audit-events")
def audit_events(page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), run_id: str | None = None, _: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    with SessionLocal() as session:
        statement = select(WorkflowEvent).order_by(WorkflowEvent.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        if run_id:
            statement = statement.where(WorkflowEvent.run_id == run_id)
        items = [_safe_model(item) for item in session.scalars(statement)]
        if not run_id:
            mcp_items = session.scalars(select(MCPRequest).order_by(MCPRequest.started_at.desc()).limit(page_size)).all()
            items.extend([{**_safe_model(item), "source": "mcp", "event_type": f"mcp.{item.status}", "node_name": item.tool_name, "run_id": None, "mcp_request_id": item.id, "mcp_client_id": item.client_id} for item in mcp_items])
    items.sort(key=lambda item: str(item.get("created_at") or item.get("started_at") or ""), reverse=True)
    return {"items": items[:page_size], "page": page, "page_size": page_size}


@router.get("/api/v1/mcp/status")
def mcp_status(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    metadata = {"server_name": "OncoAgent Platform MCP Gateway", "server_version": settings.app_version, "protocol_version": "2025-06-18", "enabled": settings.mcp_enabled, "streamable_http_enabled": settings.mcp_streamable_http_enabled, "stdio_enabled": settings.mcp_stdio_enabled, "host": settings.mcp_host, "port": settings.mcp_port, "tools": [{**item.descriptor.model_dump(), "mcp_exposed": True} for item in build_tool_registry().values()], "synthetic_data_notice": "Synthetic Synthea data only.", "clinical_validation_notice": "Not clinically validated."}
    metadata["registered_client_count"] = len(configured_clients(settings))
    return metadata


@router.get("/api/v1/mcp/clients")
def mcp_clients(settings: Settings = Depends(get_settings), _: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    return {"items": [{"client_id": item.client_id, "actor_id": item.actor_id, "actor_role": item.actor_role, "client_type": item.client_type, "dataset_ids": sorted(item.dataset_ids)} for item in configured_clients(settings).values()], "count": len(configured_clients(settings)), "development_authentication_notice": "Development-only service identity; not production OAuth."}


@router.get("/api/v1/mcp/tools")
def mcp_tools(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {"items": [{**item.descriptor.model_dump(), "mcp_exposed": True} for item in build_tool_registry().values()], "synthetic_data_notice": "Synthetic Synthea data only."}


@router.get("/api/v1/mcp/requests")
def mcp_requests(page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100), client_id: str | None = None, tool_name: str | None = None, settings: Settings = Depends(get_settings), _: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    with SessionLocal() as session:
        statement = select(MCPRequest).order_by(MCPRequest.started_at.desc()).offset((page - 1) * page_size).limit(page_size)
        if client_id:
            statement = statement.where(MCPRequest.client_id == client_id)
        if tool_name:
            statement = statement.where(MCPRequest.tool_name == tool_name)
        items = [_safe_model(item) for item in session.scalars(statement)]
    return {"items": items, "page": page, "page_size": page_size, "synthetic_data_notice": "Synthetic Synthea data only."}


@router.get("/api/v1/mcp/requests/{request_id}")
def mcp_request(request_id: str, _: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    with SessionLocal() as session:
        item = session.get(MCPRequest, request_id)
        if item is None:
            raise HTTPException(status_code=404, detail="MCP request not found")
        result = _safe_model(item)
    result["synthetic_data_notice"] = "Synthetic Synthea data only."
    result["clinical_validation_notice"] = "Not clinically validated."
    return result


@router.get("/api/v1/workflow-policy")
def workflow_policy(settings: Settings = Depends(get_settings), _: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    return {"agent_execution_enabled": settings.agent_execution_enabled, "max_candidates": settings.workflow_max_candidates, "approval_required": True, "allowed_roles": ["researcher", "reviewer", "admin"], "retrieval_policy": {"primary": "medcpt", "fallbacks": ["bioclinicalbert", "postgres_fts"], "reranker": "none"}, "synthetic_data_notice": "Synthetic Synthea data only.", "clinical_validation_notice": "Not clinically validated."}


@router.get("/api/v1/models/local-runtime")
def local_runtime_status(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    provider = OllamaQwenPlannerProvider(settings)
    health = provider.health()
    return {"runtime": "ollama", "endpoint_policy": "localhost-only", "enabled": settings.local_llm_enabled, "model": settings.local_llm_model, "status": health, "synthetic_data_notice": "Synthetic Synthea data only.", "clinical_validation_notice": "Not clinically validated."}


@router.get("/api/v1/models/planners")
def planner_statuses(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    providers: dict[str, Any] = {"deterministic": {"provider_id": "deterministic", "runtime": "python", "configured": True, "available": True, "healthy": True, "supports_structured_output": True, "limitations": ["Bounded vocabulary; unsupported requests require clarification."]}}
    for model in allowed_local_planner_models(settings):
        try:
            providers[model] = OllamaQwenPlannerProvider(settings, model_name=model).health()
        except ValueError as exc:
            providers[model] = {"provider_id": "qwen_local", "configured": False, "available": False, "healthy": False, "error": str(exc)}
    return {"providers": providers, "allowed_models": list(allowed_local_planner_models(settings)), "active_provider": settings.planner_default_provider, "configured_default_model": settings.local_planner_default_model, "fallback_provider": settings.planner_fallback_provider, "synthetic_data_notice": "Synthetic Synthea data only.", "clinical_validation_notice": "Not clinically validated."}


@router.get("/api/v1/models/planners/{provider_id}")
def planner_status(provider_id: str, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    if provider_id == "qwen_local":
        return OllamaQwenPlannerProvider(settings).health()
    if provider_id in allowed_local_planner_models(settings):
        return OllamaQwenPlannerProvider(settings, model_name=provider_id).health()
    if provider_id == "deterministic":
        return {"provider_id": "deterministic", "runtime": "python", "configured": True, "available": True, "healthy": True, "supports_structured_output": True}
    raise HTTPException(status_code=404, detail="planner provider not found")


@router.post("/api/v1/models/planners/qwen_local/smoke-test")
def planner_smoke_test(actor: ActorContext = Depends(development_actor), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    if actor.role != "admin":
        raise HTTPException(status_code=403, detail="admin role required")
    try:
        outcome = OllamaQwenPlannerProvider(settings).generate_cohort_plan("synthetic adults with hypertension", "synthetic-smoke-dataset", [Criterion(criterion_id="age-minimum", criterion_type="minimum_age", value=18, operator="gte"), Criterion(criterion_id="condition", criterion_type="condition", clinical_concept="hypertension")], 5)
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"category": getattr(exc, "category", "generation_failure"), "message": str(exc)}) from exc
    return {"provider": "qwen_local", "plan": outcome.plan.model_dump(mode="json"), "lineage": outcome.lineage, "prompt_id": "qwen_cohort_planning", "prompt_version": "phase3b-planner-v1", "prompt_length": len(PLANNING_SYSTEM_PROMPT)}


def _evaluation_output() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[4]
    for filename in ("evaluation_outputs/phase2_6_results.json", "evaluation_outputs/phase2_5_results.json"):
        path = root / filename
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            return loaded if isinstance(loaded, dict) else {"status": "invalid", "profiles": {}}
    return {"status": "not_available", "profiles": {}}


@router.get("/api/v1/evaluations")
def evaluations() -> dict[str, object]:
    output = _evaluation_output()
    return {"items": [{"evaluation_id": "phase2-6-bounded", "dataset_id": output.get("dataset_id"), "status": output.get("status", "completed"), "synthetic_development_evaluation": True, "not_clinically_validated": True}] if output.get("profiles") else [], "notice": "Synthetic development evaluation; not clinically validated or production performance."}


@router.get("/api/v1/evaluations/{evaluation_id}")
def evaluation(evaluation_id: str) -> dict[str, object]:
    if evaluation_id == "local-planners":
        return _local_planner_evaluation()
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
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _local_planner_evaluation() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[4]
    path = root / "evaluation_outputs/phase3c_local_planner_comparison.json"
    if not path.exists():
        return {"status": "not_available", "models": {}, "synthetic_development_evaluation": True, "not_clinically_validated": True}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {"status": "invalid", "models": {}}


@router.get("/api/v1/planner-policy")
def planner_policy(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    output = _local_planner_evaluation()
    policy = output.get("policy")
    if not isinstance(policy, dict):
        policy = select_policy({}, baseline=settings.local_planner_default_model)
        policy["status"] = "pending_phase3c_runtime_evaluation"
    return {"policy": policy, "evaluated_models": output.get("models", {}), "allowed_models": list(allowed_local_planner_models(settings)), "synthetic_development_evaluation": True, "not_clinically_validated": True, "not_production_performance": True}


@router.get("/api/v1/evaluations/local-planners")
def local_planner_evaluations() -> dict[str, Any]:
    return _local_planner_evaluation()


@router.get("/api/v1/evaluations/local-planners/{evaluation_id}")
def local_planner_evaluation(evaluation_id: str) -> dict[str, Any]:
    output = _local_planner_evaluation()
    if evaluation_id != output.get("evaluation_id", "phase3c-local-planners") or output.get("status") == "not_available":
        raise HTTPException(status_code=404, detail="local planner evaluation not found")
    return output


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
            implemented=["Platform health and readiness reporting", "Foundation metadata API", "Bounded clinical retrieval", "Governed LangGraph cohort workflow with human approval", "Local Qwen structured planning with deterministic fallback", "Workflow Console, Approval Queue, Audit Explorer, and Agent Catalog", "Governed MCP read-only tool gateway with stdio and Streamable HTTP"],
            planned=[
                "Bounded Synthea ingestion",
                "BioClinicalBERT retrieval",
                "Hosted LLM-backed planning providers",
                "Clinical cohort export",
                "CrewAI downstream interoperability",
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
