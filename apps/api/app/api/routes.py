import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from crewai_client.policy import validate_request as validate_crewai_request
from crewai_client.schemas import ActorContext as CrewActorContext
from crewai_client.schemas import CrewReviewRequest, CrewRunRequest
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.cross_framework.registry import framework_agents
from app.db.session import SessionLocal, get_db
from app.identity.auth import development_actor, identity_guard
from app.identity.schemas import IdentityAssignmentRequest, IdentitySummary, LocalLoginRequest
from app.identity.service import (
    AuthenticatedUser,
    authenticate_request,
    ensure_local_user,
    issue_session,
    record_access,
    require_dataset,
    require_permission,
    require_reviewer,
)
from app.mcp_identity import configured_clients
from app.models.crewai import (
    CrewEvent,
    CrewLineage,
    CrewOutput,
    CrewReview,
    CrewRun,
    CrewTask,
)
from app.models.ingestion import FhirResource
from app.models.mcp import MCPRequest
from app.models.performance import (
    PerformanceExecutionRecord,
    PerformanceFindingRecord,
    PerformanceMetricRecord,
    PerformanceSLORecord,
)
from app.models.release_evaluation import (
    ReleaseEvaluationExecution,
    ReleaseGateResult,
    ReleaseMetricResult,
)
from app.models.retrieval import ClinicalDocument, ClinicalDocumentChunk, IndexingRun
from app.models.security import SecurityAssessmentRecord, SecurityFindingRecord
from app.models.workflow import ApprovalRequest, WorkflowEvent, WorkflowRun
from app.observability.metrics import (
    PERFORMANCE_OVERLOAD_REJECTIONS,
    PERFORMANCE_QUEUE_WAIT,
    observe,
    prometheus_payload,
)
from app.observability.telemetry import observability_status
from app.performance.limits import CapacityUnavailable, workflow_capacity
from app.release_evaluation.policy import BLOCKING_GATES
from app.repositories.ingestion import (
    get_dataset,
    get_ingestion_run,
    get_patient,
    list_datasets,
    list_ingestion_runs,
    list_patients,
    patient_count,
)
from app.resilience.registry import SCENARIO_REGISTRY_VERSION, resilience_scenarios
from app.resilience.reports import load_reports
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
from app.security.audit_integrity import verify_audit_chain
from app.security.policy import SECURITY_GATE_DEFINITIONS, SECURITY_POLICY_VERSION
from app.security.retention import dry_run_retention
from app.services.crewai import _event
from app.services.crewai import cancel_run as cancel_crewai_run
from app.services.crewai import create_run as create_crewai_run
from app.services.crewai import create_run_record as create_crewai_run_record
from app.services.health import database_is_available
from app.services.timeline import timeline
from app.temporal.client import TemporalUnavailable
from app.temporal.client import connect as temporal_connect
from app.temporal.client import query_status as temporal_query_status
from app.temporal.client import run_sync as temporal_run_sync
from app.temporal.client import signal_cancel as temporal_signal_cancel
from app.temporal.client import signal_review as temporal_signal_review
from app.temporal.client import start_workflow as temporal_start_workflow
from app.temporal.contracts import TemporalCrewWorkflowInput
from app.workflow.audit import existing_decision
from app.workflow.planner import (
    PLANNING_SYSTEM_PROMPT,
    OllamaQwenPlannerProvider,
    allowed_local_planner_models,
)
from app.workflow.policy_selection import select_policy
from app.workflow.schemas import (
    ActorContext as WorkflowActorContext,
)
from app.workflow.schemas import (
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

router = APIRouter(dependencies=[Depends(identity_guard)])
ActorContext = AuthenticatedUser


@router.get("/local-oidc/.well-known/openid-configuration")
def local_oidc_configuration(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "issuer": settings.identity_issuer,
        "authorization_endpoint": f"{settings.identity_issuer}/authorize",
        "token_endpoint": f"{settings.identity_issuer}/token",
        "userinfo_endpoint": f"{settings.identity_issuer}/userinfo",
        "jwks_uri": f"{settings.identity_issuer}/jwks.json",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["HS256"],
        "local_development_only": True,
    }


@router.post("/api/v1/auth/login", response_model=IdentitySummary)
def local_login(
    request: LocalLoginRequest, response: Response, settings: Settings = Depends(get_settings)
) -> IdentitySummary:
    if not settings.identity_enabled:
        raise HTTPException(status_code=503, detail="identity authentication is disabled")
    with SessionLocal() as session:
        user = ensure_local_user(session, settings, request.user_key)
        record_access(
            session, user, "login", "session", None, "allow", "local_identity_authenticated"
        )
        token = issue_session(user, settings)
        response.set_cookie(
            settings.identity_session_cookie,
            token,
            httponly=True,
            secure=settings.identity_cookie_secure,
            samesite="lax",
            max_age=settings.identity_session_ttl_seconds,
            path="/",
        )
        return IdentitySummary(
            user_id=user.internal_id,
            subject=user.subject,
            display_name=user.display_name,
            role=user.role,
            permissions=sorted(user.permissions),
            dataset_ids=sorted(user.dataset_ids),
            issuer=user.issuer,
            expires_in_seconds=settings.identity_session_ttl_seconds,
        )


@router.post("/api/v1/auth/logout")
def local_logout(
    request: Request, response: Response, settings: Settings = Depends(get_settings)
) -> dict[str, str]:
    with SessionLocal() as session:
        try:
            user = authenticate_request(request, session, settings)
            record_access(session, user, "logout", "session", None, "allow", "session_cleared")
        except HTTPException:
            pass
    response.delete_cookie(settings.identity_session_cookie, path="/")
    return {"status": "logged_out"}


@router.get("/api/v1/auth/me", response_model=IdentitySummary)
def identity_me(
    actor: AuthenticatedUser = Depends(development_actor),
    settings: Settings = Depends(get_settings),
) -> IdentitySummary:
    return IdentitySummary(
        user_id=actor.internal_id,
        subject=actor.subject,
        display_name=actor.display_name,
        role=actor.role,
        permissions=sorted(actor.permissions),
        dataset_ids=sorted(actor.dataset_ids),
        issuer=actor.issuer,
        expires_in_seconds=settings.identity_session_ttl_seconds,
    )


@router.get("/api/v1/identity/users")
def identity_users(actor: AuthenticatedUser = Depends(development_actor)) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "identity:manage", session, action="identity_admin_read")
        from app.models.identity import DatasetGrant, Role, User, UserRole

        users = []
        for user in session.scalars(select(User).order_by(User.created_at)):
            role = session.scalar(
                select(Role.name)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user.id)
            )
            datasets = list(
                session.scalars(
                    select(DatasetGrant.dataset_id).where(
                        DatasetGrant.user_id == user.id, DatasetGrant.enabled.is_(True)
                    )
                )
            )
            users.append(
                {
                    "user_id": user.id,
                    "subject": user.external_subject,
                    "display_name": user.display_name,
                    "enabled": user.enabled,
                    "role": role,
                    "dataset_ids": datasets,
                }
            )
    return {"items": users, "local_development_only": True}


@router.post("/api/v1/identity/users/{user_id}/role")
def assign_identity_role(
    user_id: str,
    request: IdentityAssignmentRequest,
    actor: AuthenticatedUser = Depends(development_actor),
) -> dict[str, str]:
    with SessionLocal() as session:
        require_permission(actor, "identity:manage", session, action="identity_role_assign")
        from app.models.identity import Role, User, UserRole

        user = session.get(User, user_id)
        role = session.scalar(select(Role).where(Role.name == request.value))
        if user is None or role is None:
            raise HTTPException(status_code=404, detail="identity or role not found")
        assignment = session.scalar(
            select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
        )
        if assignment is None:
            session.add(UserRole(id=str(uuid4()), user_id=user_id, role_id=role.id))
        record_access(
            session,
            actor,
            "identity_role_assign",
            "user",
            user_id,
            "allow",
            "role_assignment_changed",
        )
    return {"status": "updated", "user_id": user_id, "role": request.value}


@router.post("/api/v1/identity/users/{user_id}/dataset-grants")
def assign_identity_dataset(
    user_id: str,
    request: IdentityAssignmentRequest,
    actor: AuthenticatedUser = Depends(development_actor),
) -> dict[str, str]:
    with SessionLocal() as session:
        require_permission(actor, "identity:manage", session, action="identity_dataset_grant")
        from app.models.identity import DatasetGrant, User
        from app.models.ingestion import Dataset

        if session.get(User, user_id) is None or session.get(Dataset, request.value) is None:
            raise HTTPException(status_code=404, detail="identity or dataset not found")
        grant = session.scalar(
            select(DatasetGrant).where(
                DatasetGrant.user_id == user_id, DatasetGrant.dataset_id == request.value
            )
        )
        if grant is None:
            grant = DatasetGrant(
                id=str(uuid4()),
                user_id=user_id,
                dataset_id=request.value,
                granted_by=actor.internal_id,
                enabled=request.enabled,
            )
            session.add(grant)
        else:
            grant.enabled = request.enabled
        record_access(
            session,
            actor,
            "identity_dataset_grant",
            "dataset",
            request.value,
            "allow",
            "dataset_grant_changed",
        )
    return {"status": "updated", "user_id": user_id, "dataset_id": request.value}


def _crew_actor(actor: AuthenticatedUser) -> CrewActorContext:
    return CrewActorContext(actor_id=actor.actor_id, actor_role=actor.role)


def _require_run_access(
    actor: AuthenticatedUser, dataset_id: str, creator_id: str, session: Session, *, action: str
) -> None:
    require_dataset(actor, dataset_id, session, action=action)
    if creator_id != actor.actor_id and "workflow:read-all" not in actor.permissions:
        raise HTTPException(status_code=403, detail="run access denied")


@router.get("/api/v1/crews")
def crews(
    settings: Settings = Depends(get_settings), _: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    return {
        "items": [
            {
                "name": "OncologyResearchCrew",
                "framework": "CrewAI",
                "role": "downstream MCP client",
                "enabled": settings.crewai_enabled,
                "process": "sequential",
                "human_review_required": True,
                "synthetic_data_notice": "Synthetic Synthea data only.",
                "clinical_validation_notice": "Not clinically validated.",
            }
        ]
    }


@router.get("/api/v1/crews/oncology-research/status")
def crew_status(
    settings: Settings = Depends(get_settings), _: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    return {
        "enabled": settings.crewai_enabled,
        "crew_name": "OncologyResearchCrew",
        "crewai_version": "1.15.7",
        "default_model": settings.crewai_default_model,
        "secondary_model": settings.crewai_secondary_model,
        "mcp_url": settings.crewai_mcp_url,
        "mcp_client_configured": bool(settings.crewai_mcp_client_id and settings.crewai_mcp_token),
        "process": "sequential",
        "memory": False,
        "delegation": False,
        "human_review_required": True,
        "execution_mode": settings.crewai_execution_mode,
        "temporal_enabled": settings.temporal_enabled,
        "temporal_address": settings.temporal_address if settings.temporal_enabled else None,
        "temporal_namespace": settings.temporal_namespace if settings.temporal_enabled else None,
        "temporal_task_queue": settings.temporal_task_queue if settings.temporal_enabled else None,
        "limitations": [
            "Development-only MCP identity.",
            "Legacy mode is non-durable; Temporal mode resumes only from Activity boundaries.",
            "Synthetic development output; not clinically validated.",
        ],
    }


@router.get("/api/v1/crews/oncology-research")
def crew_definition(
    settings: Settings = Depends(get_settings), _: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    return {
        "name": "OncologyResearchCrew",
        "version": "phase4b-v1",
        "agents": [
            {"role": "Cohort Researcher", "tools": ["search_clinical_documents"]},
            {
                "role": "Structured Evidence Investigator",
                "tools": [
                    "get_patient_demographics",
                    "get_patient_conditions",
                    "get_patient_observations",
                    "get_patient_procedures",
                    "get_patient_medications",
                    "get_patient_diagnostic_reports",
                    "get_patient_encounters",
                    "verify_date_window",
                ],
            },
            {
                "role": "Eligibility Evidence Reviewer",
                "tools": ["build_patient_evidence", "verify_date_window"],
            },
            {"role": "Research Brief Writer", "tools": []},
        ],
        "settings": {
            "model": settings.crewai_default_model,
            "mcp_url": settings.crewai_mcp_url,
            "human_review_required": True,
        },
    }


@router.post("/api/v1/crews/oncology-research/runs", status_code=202)
def create_crew_run(
    request: CrewRunRequest,
    actor: ActorContext = Depends(development_actor),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if not settings.crewai_enabled:
        raise HTTPException(status_code=503, detail="CrewAI is disabled by platform policy")
    if not settings.crewai_mcp_client_id or not settings.crewai_mcp_token:
        raise HTTPException(status_code=503, detail="CrewAI MCP client is not configured")
    with SessionLocal() as session:
        require_permission(actor, "workflow:create", session, action="crew_run_create")
        require_dataset(actor, request.dataset_id, session, action="crew_run_create")
    if (
        request.actor_context.actor_id != actor.actor_id
        or request.actor_context.actor_role != actor.role
    ):
        # The authenticated session is authoritative.  Rejecting a mismatch
        # makes privilege-escalation attempts explicit while preserving a
        # sanitized contract for every accepted request.
        raise HTTPException(
            status_code=403, detail="request actor context does not match authenticated identity"
        )
    if actor.role not in {"researcher", "reviewer", "administrator"}:
        raise HTTPException(
            status_code=403, detail="identity is not authorized to run CrewAI research"
        )
    request = request.model_copy(
        update={
            "actor_context": CrewActorContext(
                actor_id=actor.actor_id,
                actor_role="admin" if actor.role == "administrator" else actor.role,
            )
        }
    )
    try:
        validate_crewai_request(
            request, {item for item in settings.crewai_mcp_dataset_ids.split(",") if item}
        )
        if settings.crewai_execution_mode == "temporal":
            if not settings.temporal_enabled:
                raise HTTPException(
                    status_code=503, detail="Temporal execution is disabled by policy"
                )
            try:
                with workflow_capacity().acquire(
                    settings.performance_queue_timeout_seconds
                ) as wait:
                    observe(PERFORMANCE_QUEUE_WAIT, wait, {"queue": "workflow"})
                    run = create_crewai_run_record(request, settings, "temporal")
            except CapacityUnavailable as exc:
                observe(
                    PERFORMANCE_OVERLOAD_REJECTIONS,
                    labels={"queue": "workflow", "reason": "capacity"},
                )
                raise HTTPException(
                    status_code=503, detail="workflow capacity is busy; retry later"
                ) from exc
            workflow_id = f"crewai:{run.id}"
            with SessionLocal.begin() as session:
                persisted = session.get(CrewRun, run.id)
                if persisted:
                    persisted.temporal_workflow_id = workflow_id
                    persisted.temporal_namespace = settings.temporal_namespace
                    persisted.temporal_task_queue = settings.temporal_task_queue
                    persisted.temporal_execution_status = "starting"
                    persisted.temporal_current_stage = "create_or_load_run"
                    persisted.temporal_correlation_id = run.correlation_id
            workflow_input = TemporalCrewWorkflowInput(
                run_id=run.id,
                request=request.model_dump(mode="json"),
                temporal_workflow_id=workflow_id,
                correlation_id=run.correlation_id,
            )
            try:
                temporal_run = temporal_run_sync(temporal_start_workflow, settings, workflow_input)
            except TemporalUnavailable as exc:
                with SessionLocal.begin() as session:
                    failed = session.get(CrewRun, run.id)
                    if failed:
                        failed.status = "failed"
                        failed.error_category = "temporal_unavailable"
                        failed.error_message = "Temporal execution is unavailable"
                        failed.temporal_execution_status = "unavailable"
                        failed.temporal_failure_type = "temporal_unavailable"
                raise HTTPException(
                    status_code=503, detail="Temporal execution is unavailable"
                ) from exc
            with SessionLocal.begin() as session:
                persisted = session.get(CrewRun, run.id)
                if persisted:
                    persisted.temporal_run_id = temporal_run.get("run_id")
                    persisted.temporal_execution_status = "running"
            run = _crew_get(run.id)
        else:
            try:
                with workflow_capacity().acquire(
                    settings.performance_queue_timeout_seconds
                ) as wait:
                    observe(PERFORMANCE_QUEUE_WAIT, wait, {"queue": "workflow"})
                    run = create_crewai_run(request, settings)
            except CapacityUnavailable as exc:
                observe(
                    PERFORMANCE_OVERLOAD_REJECTIONS,
                    labels={"queue": "workflow", "reason": "capacity"},
                )
                raise HTTPException(
                    status_code=503, detail="workflow capacity is busy; retry later"
                ) from exc
        return {
            "run_id": run.id,
            "status": run.status,
            "execution_mode": run.temporal_execution_mode,
            "temporal_workflow_id": run.temporal_workflow_id,
            "temporal_run_id": run.temporal_run_id,
            "temporal_ui_url": settings.temporal_ui_url
            if run.temporal_execution_mode == "temporal"
            else None,
            "created_at": run.created_at,
            "links": {
                "self": f"/api/v1/crews/oncology-research/runs/{run.id}",
                "events": f"/api/v1/crews/oncology-research/runs/{run.id}/events",
                "output": f"/api/v1/crews/oncology-research/runs/{run.id}/output",
                "temporal": f"/api/v1/crews/oncology-research/runs/{run.id}/temporal",
            },
        }
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _crew_get(run_id: str) -> CrewRun:
    with SessionLocal() as session:
        run = session.get(CrewRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="CrewAI run not found")
    return run


def _authorized_crew_get(run_id: str, actor: AuthenticatedUser) -> CrewRun:
    run = _crew_get(run_id)
    with SessionLocal() as session:
        _require_run_access(actor, run.dataset_id, run.actor_id, session, action="crew_run_read")
    return run


def _review_authorized_crew_get(
    run_id: str, actor: AuthenticatedUser, *, deciding: bool = False
) -> CrewRun:
    """Authorize review access independently of ordinary run ownership.

    The creator can inspect their own review, while an assigned reviewer can
    inspect or decide it with review permissions and the dataset grant.  No
    reviewer is granted general run read access by this path.
    """
    run = _crew_get(run_id)
    with SessionLocal() as session:
        require_dataset(actor, run.dataset_id, session, action="crew_review_dataset_access")
        is_creator = actor.actor_id == run.actor_id or actor.internal_id == run.actor_id
        if is_creator:
            require_permission(actor, "workflow:read-own", session, action="crew_review_read")
            if deciding:
                record_access(
                    session, actor, "review_decision", "review", run_id, "deny", "self_approval"
                )
                raise HTTPException(
                    status_code=403, detail="researcher cannot approve their own run"
                )
        else:
            if not deciding:
                require_permission(
                    actor, "review:read-assigned", session, action="crew_review_read"
                )
            require_reviewer(
                actor,
                run.dataset_id,
                session,
                run.actor_id,
                action="crew_review_decision" if deciding else "crew_review_read",
            )
    return run


@router.get("/api/v1/crews/oncology-research/runs")
def list_crew_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    dataset_id: str | None = None,
    _: ActorContext = Depends(development_actor),
) -> dict[str, Any]:
    actor = _
    with SessionLocal() as session:
        if dataset_id:
            require_dataset(actor, dataset_id, session, action="crew_run_list")
        statement = (
            select(CrewRun)
            .where(CrewRun.dataset_id.in_(actor.dataset_ids))
            .order_by(CrewRun.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        if dataset_id:
            statement = statement.where(CrewRun.dataset_id == dataset_id)
        items = [_safe_model(item) for item in session.scalars(statement)]
    return {"items": items, "page": page, "page_size": page_size}


@router.get("/api/v1/crews/oncology-research/runs/{run_id}")
def crew_run(run_id: str, _: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    actor = _
    run = _crew_get(run_id)
    with SessionLocal() as session:
        _require_run_access(actor, run.dataset_id, run.actor_id, session, action="crew_run_read")
    return _safe_model(run)


@router.get("/api/v1/crews/oncology-research/runs/{run_id}/events")
def crew_events(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    actor: ActorContext = Depends(development_actor),
) -> dict[str, Any]:
    _authorized_crew_get(run_id, actor)
    with SessionLocal() as session:
        items = list(
            session.scalars(
                select(CrewEvent)
                .where(CrewEvent.crew_run_id == run_id)
                .order_by(CrewEvent.created_at)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
    return {"items": [_safe_model(item) for item in items], "page": page, "page_size": page_size}


@router.get("/api/v1/crews/oncology-research/runs/{run_id}/tasks")
def crew_tasks(run_id: str, actor: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    _authorized_crew_get(run_id, actor)
    with SessionLocal() as session:
        items = list(
            session.scalars(
                select(CrewTask).where(CrewTask.crew_run_id == run_id).order_by(CrewTask.task_name)
            )
        )
    return {"items": [_safe_model(item) for item in items]}


@router.get("/api/v1/crews/oncology-research/runs/{run_id}/output")
def crew_output(run_id: str, actor: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    _authorized_crew_get(run_id, actor)
    with SessionLocal() as session:
        item = session.scalar(select(CrewOutput).where(CrewOutput.crew_run_id == run_id))
    if item is None:
        raise HTTPException(status_code=404, detail="CrewAI output is not available")
    return {
        "output_type": item.output_type,
        "schema_version": item.schema_version,
        "output": item.output_json,
    }


@router.get("/api/v1/crews/oncology-research/runs/{run_id}/lineage")
def crew_lineage(run_id: str, actor: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    _authorized_crew_get(run_id, actor)
    with SessionLocal() as session:
        item = session.scalar(select(CrewLineage).where(CrewLineage.crew_run_id == run_id))
    if item is None:
        raise HTTPException(status_code=404, detail="CrewAI lineage is not available")
    return _safe_model(item)


@router.post("/api/v1/crews/oncology-research/runs/{run_id}/cancel")
def cancel_crew(run_id: str, actor: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    run_before = _authorized_crew_get(run_id, actor)
    with SessionLocal() as session:
        require_dataset(actor, run_before.dataset_id, session, action="crew_cancel")
        if run_before.actor_id == actor.actor_id:
            require_permission(actor, "workflow:cancel-own", session, action="crew_cancel")
        else:
            require_permission(actor, "workflow:cancel-any", session, action="crew_cancel")
    if run_before.temporal_execution_mode == "temporal":
        if not run_before.temporal_workflow_id:
            raise HTTPException(status_code=409, detail="Temporal workflow has not started")
        try:
            with SessionLocal.begin() as session:
                persisted = session.get(CrewRun, run_id)
                if persisted:
                    persisted.status = "cancellation_requested"
                    persisted.temporal_execution_status = "cancellation_requested"
            temporal_run_sync(
                temporal_signal_cancel, get_settings(), run_before.temporal_workflow_id
            )
        except TemporalUnavailable as exc:
            raise HTTPException(
                status_code=503, detail="Temporal execution is unavailable"
            ) from exc
        return {"run_id": run_id, "status": "cancellation_requested", "execution_mode": "temporal"}
    try:
        run = cancel_crewai_run(run_id, actor.actor_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=404, detail="CrewAI run not found")
    return _safe_model(run)


@router.get("/api/v1/crews/oncology-research/runs/{run_id}/review")
def get_crew_review(
    run_id: str, actor: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    _review_authorized_crew_get(run_id, actor)
    with SessionLocal() as session:
        item = session.scalar(select(CrewReview).where(CrewReview.crew_run_id == run_id))
    if item is None:
        raise HTTPException(status_code=404, detail="CrewAI review not found")
    return _safe_model(item)


@router.post("/api/v1/crews/oncology-research/runs/{run_id}/review")
def review_crew(
    run_id: str, decision: CrewReviewRequest, actor: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    run = _review_authorized_crew_get(run_id, actor, deciding=decision.decision != "cancel")
    with SessionLocal() as session:
        if decision.decision == "cancel" and actor.actor_id == run.actor_id:
            require_permission(actor, "workflow:cancel-own", session, action="crew_review_cancel")
            require_dataset(actor, run.dataset_id, session, action="crew_review_cancel")
        elif decision.decision == "cancel":
            require_reviewer(
                actor, run.dataset_id, session, run.actor_id, action="crew_review_cancel"
            )
    if run.temporal_execution_mode == "temporal":
        with SessionLocal() as session:
            item = session.scalar(select(CrewReview).where(CrewReview.crew_run_id == run_id))
        if item is None:
            raise HTTPException(status_code=409, detail="CrewAI output is not awaiting review")
        if item.status != "pending":
            raise HTTPException(status_code=409, detail="CrewAI review already has a decision")
        if not run.temporal_workflow_id:
            raise HTTPException(status_code=409, detail="Temporal workflow has not started")
        try:
            temporal_run_sync(
                temporal_signal_review,
                get_settings(),
                run.temporal_workflow_id,
                {
                    "decision": decision.decision,
                    "comment": decision.comment,
                    "reviewer_id": actor.actor_id,
                    "reviewer_role": actor.role,
                },
            )
        except TemporalUnavailable as exc:
            raise HTTPException(
                status_code=503, detail="Temporal execution is unavailable"
            ) from exc
        return {"run_id": run_id, "status": "review_signaled", "review_status": decision.decision}
    with SessionLocal.begin() as session:
        item = session.scalar(select(CrewReview).where(CrewReview.crew_run_id == run_id))
        if item is None:
            raise HTTPException(status_code=409, detail="CrewAI output is not awaiting review")
        if item.status != "pending":
            raise HTTPException(status_code=409, detail="CrewAI review already has a decision")
        (
            item.status,
            item.reviewer_id,
            item.reviewer_role,
            item.decision,
            item.comment,
            item.decided_at,
        ) = (
            "decided",
            actor.actor_id,
            actor.role,
            decision.decision,
            decision.comment,
            datetime.now(UTC),
        )
        persisted_run = session.get(CrewRun, run_id)
        if persisted_run is None:
            raise HTTPException(status_code=404, detail="CrewAI run not found")
        persisted_run.status = {
            "accept_for_synthetic_research": "accepted",
            "reject": "rejected",
            "request_changes": "awaiting_human_review",
            "cancel": "cancelled",
        }[decision.decision]
        _event(
            session,
            run_id,
            "review_decided",
            {"decision": decision.decision, "reviewer_role": actor.role},
        )
        final_status = persisted_run.status
    return {"run_id": run_id, "status": final_status, "review_status": decision.decision}


@router.get("/api/v1/crews/oncology-research/runs/{run_id}/temporal")
def crew_temporal_status(
    run_id: str, _: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    run = _crew_get(run_id)
    if run.temporal_execution_mode != "temporal" or not run.temporal_workflow_id:
        return {
            "execution_mode": run.temporal_execution_mode,
            "available": False,
            "status": run.status,
        }
    try:
        status_data = temporal_run_sync(
            temporal_query_status, get_settings(), run.temporal_workflow_id
        )
    except TemporalUnavailable:
        status_data = {"status": "temporal_unavailable"}
    return {
        "execution_mode": "temporal",
        "available": status_data.get("status") != "temporal_unavailable",
        "workflow_id": run.temporal_workflow_id,
        "temporal_run_id": run.temporal_run_id,
        "namespace": run.temporal_namespace,
        "task_queue": run.temporal_task_queue,
        "ui_url": get_settings().temporal_ui_url,
        "application": _safe_model(run),
        "workflow": status_data,
    }


@router.get("/api/v1/temporal/status")
def temporal_status(
    settings: Settings = Depends(get_settings), actor: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "temporal:read", session, action="temporal_status_read")
    if not settings.temporal_enabled:
        return {
            "enabled": False,
            "available": False,
            "address": settings.temporal_address,
            "namespace": settings.temporal_namespace,
        }
    try:
        temporal_run_sync(temporal_connect, settings)
    except TemporalUnavailable:
        return {
            "enabled": True,
            "available": False,
            "address": settings.temporal_address,
            "namespace": settings.temporal_namespace,
            "task_queue": settings.temporal_task_queue,
        }
    return {
        "enabled": True,
        "available": True,
        "address": settings.temporal_address,
        "namespace": settings.temporal_namespace,
        "task_queue": settings.temporal_task_queue,
        "ui_url": settings.temporal_ui_url,
    }


def _run_response(run: WorkflowRun) -> RunResponse:
    return RunResponse(
        run_id=run.id,
        thread_id=run.thread_id,
        status=run.status,
        current_node=run.current_node,
        created_at=run.created_at,
        dataset_id=run.dataset_id,
        actor_id=run.actor_id,
        actor_role=run.actor_role,
        approval_id=run.approval_id,
        structured_plan=run.structured_plan,
        planner_lineage=run.planner_lineage,
        final_result=run.final_result,
        warnings=run.warnings,
        errors=run.errors,
        links={
            "self": f"/api/v1/runs/{run.id}",
            "events": f"/api/v1/runs/{run.id}/events",
            "evidence": f"/api/v1/runs/{run.id}/evidence",
            "candidates": f"/api/v1/runs/{run.id}/candidates",
        },
    )


def _safe_model(item: Any) -> dict[str, Any]:
    return {
        key: (value.isoformat() if hasattr(value, "isoformat") else value)
        for key, value in item.__dict__.items()
        if not key.startswith("_")
    }


@router.post("/api/v1/runs", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
def create_workflow_run(
    request: RunCreateRequest,
    actor: ActorContext = Depends(development_actor),
    settings: Settings = Depends(get_settings),
) -> RunResponse:
    try:
        with SessionLocal() as session:
            require_permission(actor, "workflow:create", session, action="workflow_create")
            require_dataset(actor, request.dataset_id, session, action="workflow_create")
        workflow_actor = WorkflowActorContext.model_validate(
            {"actor_id": actor.actor_id, "role": actor.role}
        )
        try:
            with workflow_capacity().acquire(settings.performance_queue_timeout_seconds) as wait:
                observe(PERFORMANCE_QUEUE_WAIT, wait, {"queue": "workflow"})
                return _run_response(create_run(request, workflow_actor, settings))
        except CapacityUnavailable as exc:
            observe(
                PERFORMANCE_OVERLOAD_REJECTIONS,
                labels={"queue": "workflow", "reason": "capacity"},
            )
            raise HTTPException(
                status_code=503, detail="workflow capacity is busy; retry later"
            ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/api/v1/runs")
def list_workflow_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    dataset_id: str | None = None,
    actor: ActorContext = Depends(development_actor),
) -> dict[str, Any]:
    with SessionLocal() as session:
        if dataset_id:
            require_dataset(actor, dataset_id, session, action="workflow_list")
        statement = (
            select(WorkflowRun)
            .where(WorkflowRun.dataset_id.in_(actor.dataset_ids))
            .order_by(WorkflowRun.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        if dataset_id:
            statement = statement.where(WorkflowRun.dataset_id == dataset_id)
        items = [_safe_model(item) for item in session.scalars(statement)]
    return {"items": items, "page": page, "page_size": page_size}


@router.get("/api/v1/runs/{run_id}/events")
def workflow_events(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    actor: ActorContext = Depends(development_actor),
) -> dict[str, Any]:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="workflow run not found")
    with SessionLocal() as session:
        _require_run_access(
            actor, run.dataset_id, run.actor_id, session, action="workflow_events_read"
        )
    items = list_events(run_id)
    start = (page - 1) * page_size
    return {
        "items": [_safe_model(item) for item in items[start : start + page_size]],
        "page": page,
        "page_size": page_size,
    }


@router.get("/api/v1/runs/{run_id}/evidence")
def workflow_evidence(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    actor: ActorContext = Depends(development_actor),
) -> dict[str, Any]:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="workflow run not found")
    with SessionLocal() as session:
        _require_run_access(
            actor, run.dataset_id, run.actor_id, session, action="workflow_evidence_read"
        )
        require_permission(actor, "evidence:read", session, action="workflow_evidence_read")
    items = list_evidence(run_id)
    start = (page - 1) * page_size
    return {
        "items": [_safe_model(item) for item in items[start : start + page_size]],
        "page": page,
        "page_size": page_size,
    }


@router.get("/api/v1/runs/{run_id}/candidates")
def workflow_candidates(
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    actor: ActorContext = Depends(development_actor),
) -> dict[str, Any]:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="workflow run not found")
    with SessionLocal() as session:
        _require_run_access(
            actor, run.dataset_id, run.actor_id, session, action="workflow_candidates_read"
        )
    items = list_candidates(run_id)
    start = (page - 1) * page_size
    return {
        "items": [_safe_model(item) for item in items[start : start + page_size]],
        "page": page,
        "page_size": page_size,
    }


@router.get("/api/v1/runs/{run_id}/stream")
def workflow_stream(run_id: str, _: ActorContext = Depends(development_actor)) -> StreamingResponse:
    if get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="workflow run not found")

    def stream() -> Any:
        for item in list_events(run_id):
            yield f"event: {item.event_type}\ndata: {json.dumps(_safe_model(item), default=str)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/api/v1/runs/{run_id}", response_model=RunResponse)
def workflow_run(run_id: str, actor: ActorContext = Depends(development_actor)) -> RunResponse:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="workflow run not found")
    with SessionLocal() as session:
        _require_run_access(actor, run.dataset_id, run.actor_id, session, action="workflow_read")
    return _run_response(run)


@router.post("/api/v1/runs/{run_id}/cancel", response_model=RunResponse)
def cancel_workflow_run(
    run_id: str,
    actor: ActorContext = Depends(development_actor),
    settings: Settings = Depends(get_settings),
) -> RunResponse:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="workflow run not found")
    if run.status in {"completed", "rejected", "cancelled", "failed", "needs_clarification"}:
        raise HTTPException(status_code=409, detail="terminal workflow runs cannot be cancelled")
    with SessionLocal() as session:
        require_dataset(actor, run.dataset_id, session, action="workflow_cancel")
        if actor.actor_id == run.actor_id:
            require_permission(actor, "workflow:cancel-own", session, action="workflow_cancel")
        else:
            require_permission(actor, "workflow:cancel-any", session, action="workflow_cancel")
    if not run.approval_id:
        raise HTTPException(status_code=409, detail="run is not at a cancellable checkpoint")
    try:
        return _run_response(
            resume_run(
                run,
                {
                    "decision": "cancel",
                    "actor_id": actor.actor_id,
                    "actor_role": actor.role,
                    "comment": "Cancelled by actor.",
                },
                settings,
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/api/v1/approvals")
def approvals(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    actor: ActorContext = Depends(development_actor),
) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "review:read-assigned", session, action="review_queue_read")
    with SessionLocal() as session:
        items = list(
            session.scalars(
                select(ApprovalRequest)
                .join(WorkflowRun, WorkflowRun.id == ApprovalRequest.run_id)
                .where(WorkflowRun.dataset_id.in_(actor.dataset_ids))
                .order_by(ApprovalRequest.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
    return {"items": [_safe_model(item) for item in items], "page": page, "page_size": page_size}


@router.get("/api/v1/approvals/{approval_id}")
def approval(approval_id: str, actor: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    item = get_approval_request(approval_id)
    if item is None:
        raise HTTPException(status_code=404, detail="approval request not found")
    run = get_run(item.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="workflow run not found")
    with SessionLocal() as session:
        require_permission(actor, "review:read-assigned", session, action="review_read")
        require_dataset(actor, run.dataset_id, session, action="review_read")
    return _safe_model(item)


@router.post("/api/v1/approvals/{approval_id}/decision", response_model=RunResponse)
def approval_decision(
    approval_id: str,
    request: ApprovalDecisionRequest,
    actor: ActorContext = Depends(development_actor),
    settings: Settings = Depends(get_settings),
) -> RunResponse:
    approval_item = get_approval_request(approval_id)
    if approval_item is None:
        raise HTTPException(status_code=404, detail="approval request not found")
    run = get_run(approval_item.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="workflow run not found")
    with SessionLocal() as session:
        if request.decision == "cancel" and actor.actor_id == run.actor_id:
            require_permission(actor, "workflow:cancel-own", session, action="approval_cancel")
            require_dataset(actor, run.dataset_id, session, action="approval_cancel")
        else:
            require_reviewer(actor, run.dataset_id, session, run.actor_id)
    if run.status in {"completed", "rejected", "cancelled", "failed", "needs_clarification"}:
        raise HTTPException(status_code=409, detail="workflow run is terminal")
    if existing_decision(approval_id) is not None:
        raise HTTPException(status_code=409, detail="approval already has a decision")
    if request.decision == "approve" and actor.actor_id == run.actor_id:
        raise HTTPException(
            status_code=403, detail="researcher and reviewer must be different actors"
        )
    try:
        return _run_response(
            resume_run(
                run,
                {
                    "decision": request.decision,
                    "actor_id": actor.actor_id,
                    "actor_role": actor.role,
                    "comment": request.comment,
                },
                settings,
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/api/v1/audit-events")
def audit_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    run_id: str | None = None,
    framework: str | None = None,
    source: str | None = None,
    mcp_correlation_status: str | None = None,
    governance_violation: bool | None = None,
    missing_provenance: bool | None = None,
    task_correlation_failure: bool | None = None,
    dataset_mismatch: bool | None = None,
    missing_lifecycle_event: bool | None = None,
    actor: ActorContext = Depends(development_actor),
) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "audit:read", session, action="audit_read")
    with SessionLocal() as session:
        statement = (
            select(WorkflowEvent)
            .order_by(WorkflowEvent.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        if run_id:
            statement = statement.where(WorkflowEvent.run_id == run_id)
        items = [_safe_model(item) for item in session.scalars(statement)]
        if not run_id:
            mcp_items = session.scalars(
                select(MCPRequest).order_by(MCPRequest.started_at.desc()).limit(page_size)
            ).all()
            items.extend(
                [
                    {
                        **_safe_model(item),
                        "source": "mcp",
                        "event_type": f"mcp.{item.status}",
                        "node_name": item.tool_name,
                        "run_id": None,
                        "mcp_request_id": item.id,
                        "mcp_client_id": item.client_id,
                    }
                    for item in mcp_items
                ]
            )
            crew_items = session.scalars(
                select(CrewEvent).order_by(CrewEvent.created_at.desc()).limit(page_size)
            ).all()
            items.extend(
                [
                    {
                        **_safe_model(item),
                        "source": "crewai",
                        "event_type": f"crewai.{item.event_type}",
                        "node_name": item.task_name,
                        "run_id": item.crew_run_id,
                        "crew_event_id": item.id,
                    }
                    for item in crew_items
                ]
            )
    items.sort(
        key=lambda item: str(item.get("created_at") or item.get("started_at") or ""), reverse=True
    )
    if source:
        items = [item for item in items if item.get("source", "workflow") == source]
    if framework:
        items = [
            item
            for item in items
            if item.get("framework") == framework
            or item.get("source") == framework
            or (framework == "langgraph" and item.get("source", "workflow") == "workflow")
        ]
    if mcp_correlation_status == "orphan":
        items = [item for item in items if item.get("mcp_correlation_status") == "orphan"]
    if governance_violation is True:
        items = [item for item in items if item.get("governance_violation") is True]
    for key, enabled in (
        ("missing_provenance", missing_provenance),
        ("task_correlation_failure", task_correlation_failure),
        ("dataset_mismatch", dataset_mismatch),
        ("missing_lifecycle_event", missing_lifecycle_event),
    ):
        if enabled is True:
            items = [item for item in items if item.get(key) is True]
    return {"items": items[:page_size], "page": page, "page_size": page_size}


@router.get("/api/v1/mcp/status")
def mcp_status(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    metadata = {
        "server_name": "OncoAgent Platform MCP Gateway",
        "server_version": settings.app_version,
        "protocol_version": "2025-06-18",
        "enabled": settings.mcp_enabled,
        "streamable_http_enabled": settings.mcp_streamable_http_enabled,
        "stdio_enabled": settings.mcp_stdio_enabled,
        "host": settings.mcp_host,
        "port": settings.mcp_port,
        "tools": [
            {**item.descriptor.model_dump(), "mcp_exposed": True}
            for item in build_tool_registry().values()
        ],
        "synthetic_data_notice": "Synthetic Synthea data only.",
        "clinical_validation_notice": "Not clinically validated.",
    }
    metadata["registered_client_count"] = len(configured_clients(settings))
    return metadata


@router.get("/metrics")
def metrics(settings: Settings = Depends(get_settings)) -> Response:
    if not settings.prometheus_metrics_enabled:
        raise HTTPException(status_code=404, detail="metrics disabled")
    body, media_type = prometheus_payload()
    return Response(content=body, media_type=media_type)


@router.get("/api/v1/observability/status")
def observability_endpoint(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return observability_status(settings)


@router.get("/api/v1/observability/services")
def observability_services(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "services": [
            {"service": "oncoagent-api", "status": "configured", "transport": "otlp-grpc"},
            {
                "service": "oncoagent-mcp",
                "status": "configured" if settings.mcp_enabled else "disabled",
                "transport": "streamable-http,stdio",
            },
            {
                "service": "oncoagent-crewai",
                "status": "configured" if settings.crewai_enabled else "disabled",
                "transport": "local-worker",
            },
            {"service": "oncoagent-web", "status": "configured", "transport": "http"},
            {
                "service": "oncoagent-evaluation-worker",
                "status": "configured",
                "transport": "local",
            },
        ],
        "collector_endpoint": settings.otel_exporter_otlp_endpoint,
        "synthetic_data_notice": "Synthetic Synthea data only.",
        "clinical_validation_notice": "Not clinically validated.",
    }


@router.get("/api/v1/observability/metrics-summary")
def observability_metrics_summary(_: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    with SessionLocal() as session:
        workflow_count = session.query(WorkflowRun).count()
        crew_count = session.query(CrewRun).count()
        mcp_count = session.query(MCPRequest).count()
    return {
        "workflow_runs": workflow_count,
        "crewai_runs": crew_count,
        "mcp_requests": mcp_count,
        "metric_endpoint": "/metrics",
        "labels_are_low_cardinality": True,
        "synthetic_data_notice": "Synthetic Synthea data only.",
        "clinical_validation_notice": "Not clinically validated.",
    }


@router.get("/api/v1/observability/configuration")
def observability_configuration(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "enabled": settings.observability_enabled,
        "service_name": settings.otel_service_name,
        "trace_sample_ratio": settings.otel_trace_sample_ratio,
        "metrics_enabled": settings.prometheus_metrics_enabled,
        "metrics_path": settings.prometheus_metrics_path,
        "collector_available_is_non_fatal": True,
        "redaction": {
            "prompts": True,
            "raw_fhir": True,
            "credentials": True,
            "patient_ids_in_metrics": True,
        },
    }


@router.get("/api/v1/resilience/scenarios")
def resilience_scenario_catalog(actor: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "resilience:read", session, action="resilience_read")
    return {
        "registry_version": SCENARIO_REGISTRY_VERSION,
        "items": [item.model_dump() for item in resilience_scenarios()],
        "synthetic_data_notice": "Synthetic Synthea data only.",
        "clinical_validation_notice": "Not clinically validated.",
    }


@router.get("/api/v1/resilience/certifications")
def resilience_certifications(actor: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "resilience:read", session, action="resilience_read")
    reports = load_reports()
    return {"items": reports, "count": len(reports), "registry_version": SCENARIO_REGISTRY_VERSION}


@router.get("/api/v1/resilience/certifications/{certification_id}")
def resilience_certification(
    certification_id: str, actor: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "resilience:read", session, action="resilience_read")
    for report in load_reports():
        if report.get("certification_id") == certification_id:
            return report
    raise HTTPException(status_code=404, detail="resilience certification not found")


@router.get("/api/v1/resilience/readiness")
def resilience_readiness(
    settings: Settings = Depends(get_settings), _: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    return {
        "ready": settings.temporal_enabled and settings.crewai_execution_mode == "temporal",
        "execution_mode": settings.crewai_execution_mode,
        "fault_injection_enabled_by_default": False,
        "registry_version": SCENARIO_REGISTRY_VERSION,
        "limitations": ["Certification is local synthetic development validation."],
    }


@router.get("/api/v1/mcp/clients")
def mcp_clients(
    settings: Settings = Depends(get_settings), _: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    return {
        "items": [
            {
                "client_id": item.client_id,
                "actor_id": item.actor_id,
                "actor_role": item.actor_role,
                "client_type": item.client_type,
                "dataset_ids": sorted(item.dataset_ids),
            }
            for item in configured_clients(settings).values()
        ],
        "count": len(configured_clients(settings)),
        "development_authentication_notice": "Development-only service identity; not production OAuth.",
    }


@router.get("/api/v1/mcp/tools")
def mcp_tools(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "items": [
            {**item.descriptor.model_dump(), "mcp_exposed": True}
            for item in build_tool_registry().values()
        ],
        "synthetic_data_notice": "Synthetic Synthea data only.",
    }


@router.get("/api/v1/mcp/requests")
def mcp_requests(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    client_id: str | None = None,
    tool_name: str | None = None,
    settings: Settings = Depends(get_settings),
    _: ActorContext = Depends(development_actor),
) -> dict[str, Any]:
    with SessionLocal() as session:
        statement = (
            select(MCPRequest)
            .order_by(MCPRequest.started_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        if client_id:
            statement = statement.where(MCPRequest.client_id == client_id)
        if tool_name:
            statement = statement.where(MCPRequest.tool_name == tool_name)
        items = [_safe_model(item) for item in session.scalars(statement)]
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "synthetic_data_notice": "Synthetic Synthea data only.",
    }


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
def workflow_policy(
    settings: Settings = Depends(get_settings), _: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    return {
        "agent_execution_enabled": settings.agent_execution_enabled,
        "max_candidates": settings.workflow_max_candidates,
        "approval_required": True,
        "allowed_roles": ["researcher", "reviewer", "admin"],
        "retrieval_policy": {
            "primary": "medcpt",
            "fallbacks": ["bioclinicalbert", "postgres_fts"],
            "reranker": "none",
        },
        "synthetic_data_notice": "Synthetic Synthea data only.",
        "clinical_validation_notice": "Not clinically validated.",
    }


@router.get("/api/v1/models/local-runtime")
def local_runtime_status(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    provider = OllamaQwenPlannerProvider(settings)
    health = provider.health()
    return {
        "runtime": "ollama",
        "endpoint_policy": "localhost-only",
        "enabled": settings.local_llm_enabled,
        "model": settings.local_llm_model,
        "status": health,
        "synthetic_data_notice": "Synthetic Synthea data only.",
        "clinical_validation_notice": "Not clinically validated.",
    }


@router.get("/api/v1/models/planners")
def planner_statuses(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    providers: dict[str, Any] = {
        "deterministic": {
            "provider_id": "deterministic",
            "runtime": "python",
            "configured": True,
            "available": True,
            "healthy": True,
            "supports_structured_output": True,
            "limitations": ["Bounded vocabulary; unsupported requests require clarification."],
        }
    }
    for model in allowed_local_planner_models(settings):
        try:
            providers[model] = OllamaQwenPlannerProvider(settings, model_name=model).health()
        except ValueError as exc:
            providers[model] = {
                "provider_id": "qwen_local",
                "configured": False,
                "available": False,
                "healthy": False,
                "error": str(exc),
            }
    return {
        "providers": providers,
        "allowed_models": list(allowed_local_planner_models(settings)),
        "active_provider": settings.planner_default_provider,
        "configured_default_model": settings.local_planner_default_model,
        "fallback_provider": settings.planner_fallback_provider,
        "synthetic_data_notice": "Synthetic Synthea data only.",
        "clinical_validation_notice": "Not clinically validated.",
    }


@router.get("/api/v1/models/planners/{provider_id}")
def planner_status(provider_id: str, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    if provider_id == "qwen_local":
        return OllamaQwenPlannerProvider(settings).health()
    if provider_id in allowed_local_planner_models(settings):
        return OllamaQwenPlannerProvider(settings, model_name=provider_id).health()
    if provider_id == "deterministic":
        return {
            "provider_id": "deterministic",
            "runtime": "python",
            "configured": True,
            "available": True,
            "healthy": True,
            "supports_structured_output": True,
        }
    raise HTTPException(status_code=404, detail="planner provider not found")


@router.post("/api/v1/models/planners/qwen_local/smoke-test")
def planner_smoke_test(
    actor: ActorContext = Depends(development_actor), settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    if actor.role != "admin":
        raise HTTPException(status_code=403, detail="admin role required")
    try:
        outcome = OllamaQwenPlannerProvider(settings).generate_cohort_plan(
            "synthetic adults with hypertension",
            "synthetic-smoke-dataset",
            [
                Criterion(
                    criterion_id="age-minimum",
                    criterion_type="minimum_age",
                    value=18,
                    operator="gte",
                ),
                Criterion(
                    criterion_id="condition",
                    criterion_type="condition",
                    clinical_concept="hypertension",
                ),
            ],
            5,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "category": getattr(exc, "category", "generation_failure"),
                "message": str(exc),
            },
        ) from exc
    return {
        "provider": "qwen_local",
        "plan": outcome.plan.model_dump(mode="json"),
        "lineage": outcome.lineage,
        "prompt_id": "qwen_cohort_planning",
        "prompt_version": "phase3b-planner-v1",
        "prompt_length": len(PLANNING_SYSTEM_PROMPT),
    }


@router.get("/api/v1/security/policy")
def security_policy(actor: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "audit:read", session, action="security_policy_read")
    return {
        "policy_version": SECURITY_POLICY_VERSION,
        "severity_levels": ["informational", "low", "medium", "high", "critical"],
        "finding_states": [
            "open",
            "accepted_risk",
            "remediated",
            "false_positive",
            "not_applicable",
        ],
        "blocking_gates": SECURITY_GATE_DEFINITIONS,
        "scanner_unavailable": "not_evaluable; never inferred as passed",
        "limitations": [
            "Local synthetic development readiness; not HIPAA or production certification."
        ],
    }


@router.get("/api/v1/security/assessments")
def security_assessments(actor: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "audit:read", session, action="security_assessments_read")
        items = [
            _safe_model(item)
            for item in session.scalars(
                select(SecurityAssessmentRecord).order_by(
                    SecurityAssessmentRecord.created_at.desc()
                )
            ).all()
        ]
    return {"items": items, "count": len(items), "policy_version": SECURITY_POLICY_VERSION}


@router.get("/api/v1/security/assessments/{assessment_id}")
def security_assessment(
    assessment_id: str, actor: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "audit:read", session, action="security_assessment_read")
        item = session.scalar(
            select(SecurityAssessmentRecord).where(
                SecurityAssessmentRecord.assessment_id == assessment_id
            )
        )
        if item is None:
            raise HTTPException(status_code=404, detail="security assessment not found")
        findings = session.scalars(
            select(SecurityFindingRecord).where(SecurityFindingRecord.assessment_id == item.id)
        ).all()
        result = _safe_model(item)
        result["findings"] = [_safe_model(finding) for finding in findings]
    return result


@router.get("/api/v1/security/findings")
def security_findings(actor: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "audit:read", session, action="security_findings_read")
        items = [
            _safe_model(item)
            for item in session.scalars(
                select(SecurityFindingRecord).order_by(SecurityFindingRecord.severity.asc())
            ).all()
        ]
    return {"items": items, "count": len(items), "sensitive_scanner_output_excluded": True}


@router.get("/api/v1/security/audit-integrity")
def security_audit_integrity(actor: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "audit:read", session, action="security_audit_integrity_read")
        result = verify_audit_chain(session)
    return result.model_dump(mode="json")


@router.get("/api/v1/security/retention")
def security_retention(actor: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "audit:read", session, action="security_retention_read")
    return dry_run_retention()


@router.get("/api/v1/security/incident-readiness")
def security_incident_readiness(actor: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(
            actor, "audit:read", session, action="security_incident_readiness_read"
        )
    checks = [
        "credential_exposure",
        "dataset_access",
        "audit_integrity",
        "dependency_vulnerability",
        "prompt_injection",
        "worker_compromise",
        "database_compromise",
        "backup_exposure",
        "denial_of_service",
    ]
    return {
        "status": "documented",
        "checks": [{"scenario": item, "status": "documented"} for item in checks],
        "limitations": [
            "No staffed incident response team or production contact details are claimed."
        ],
    }


def _evaluation_output() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[4]
    for filename in (
        "evaluation_outputs/phase2_6_results.json",
        "evaluation_outputs/phase2_5_results.json",
    ):
        path = root / filename
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            return loaded if isinstance(loaded, dict) else {"status": "invalid", "profiles": {}}
    return {"status": "not_available", "profiles": {}}


@router.get("/api/v1/evaluations")
def evaluations() -> dict[str, object]:
    output = _evaluation_output()
    cross = _cross_framework_output()
    items: list[dict[str, Any]] = []
    if output.get("profiles"):
        items.append(
            {
                "evaluation_id": "phase2-6-bounded",
                "dataset_id": output.get("dataset_id"),
                "status": output.get("status", "completed"),
                "synthetic_development_evaluation": True,
                "not_clinically_validated": True,
            }
        )
    if cross.get("status") != "not_available":
        items.append(
            {
                "evaluation_id": "cross-framework",
                "dataset_id": cross.get("dataset_id"),
                "status": cross.get("status", "completed"),
                "synthetic_development_evaluation": True,
                "not_clinically_validated": True,
            }
        )
    return {
        "items": items,
        "notice": "Synthetic development evaluation; not clinically validated or production performance.",
    }


@router.get("/api/v1/release-evaluations")
def release_evaluations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    actor: ActorContext = Depends(development_actor),
) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "evaluation:read", session, action="release_evaluation_read")
        rows = list(
            session.scalars(
                select(ReleaseEvaluationExecution)
                .order_by(ReleaseEvaluationExecution.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
    return {
        "items": [_safe_model(item) for item in rows],
        "page": page,
        "page_size": page_size,
        "notice": "Synthetic development release evaluation; not clinically validated.",
    }


@router.get("/api/v1/release-policy")
def release_policy(actor: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "evaluation:read", session, action="release_policy_read")
    return {
        "blocking_gates": {
            name: {
                "metric": value[0],
                "threshold": value[1],
                "direction": value[2],
                "definition": value[3],
            }
            for name, value in BLOCKING_GATES.items()
        },
        "decision_values": ["approved", "blocked", "approved_with_documented_limitations"],
        "notice": "Internal synthetic development gates; not a regulatory certification.",
    }


@router.get("/api/v1/release-evaluations/{evaluation_id}")
def release_evaluation(
    evaluation_id: str, actor: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "evaluation:read", session, action="release_evaluation_read")
        item = session.get(ReleaseEvaluationExecution, evaluation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="release evaluation not found")
    return item.report_json


@router.get("/api/v1/release-evaluations/{evaluation_id}/gates")
def release_evaluation_gates(
    evaluation_id: str, actor: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "evaluation:read", session, action="release_evaluation_read")
        rows = list(
            session.scalars(
                select(ReleaseGateResult).where(ReleaseGateResult.evaluation_id == evaluation_id)
            )
        )
    if not rows:
        with SessionLocal() as session:
            if session.get(ReleaseEvaluationExecution, evaluation_id) is None:
                raise HTTPException(status_code=404, detail="release evaluation not found")
    return {
        "items": [_safe_model(item) for item in rows],
        "notice": "Required development gates; not a regulatory certification.",
    }


@router.get("/api/v1/release-evaluations/{evaluation_id}/metrics")
def release_evaluation_metrics(
    evaluation_id: str, actor: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "evaluation:read", session, action="release_evaluation_read")
        rows = list(
            session.scalars(
                select(ReleaseMetricResult).where(
                    ReleaseMetricResult.evaluation_id == evaluation_id
                )
            )
        )
    if not rows:
        with SessionLocal() as session:
            if session.get(ReleaseEvaluationExecution, evaluation_id) is None:
                raise HTTPException(status_code=404, detail="release evaluation not found")
    return {
        "items": [_safe_model(item) for item in rows],
        "notice": "N/A metrics are not inferred as passes.",
    }


@router.get("/api/v1/performance")
def performance_executions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    actor: ActorContext = Depends(development_actor),
) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "evaluation:read", session, action="performance_read")
        rows = list(
            session.scalars(
                select(PerformanceExecutionRecord)
                .order_by(PerformanceExecutionRecord.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
    return {
        "items": [_safe_model(item) for item in rows],
        "page": page,
        "page_size": page_size,
        "notice": "Synthetic development performance evaluation; local hardware-specific; not clinically validated.",
    }


@router.get("/api/v1/performance/policy")
def performance_policy(actor: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "evaluation:read", session, action="performance_policy_read")
    return {
        "contract_version": "7B.1",
        "profiles": [
            "api-read-light",
            "api-read-concurrent",
            "langgraph-cohort",
            "crewai-temporal",
            "mcp-read",
            "mixed-platform",
            "cancellation-load",
            "retry-recovery",
            "authorization-denial",
            "model-saturation",
        ],
        "blocking_correctness_gates": {
            "authorization_bypass_rate": 0,
            "duplicate_business_record_rate": 0,
            "orphan_mcp_request_rate": 0,
            "cancellation_finalization_rate": 0,
            "policy_denial_retry_rate": 0,
            "telemetry_redaction_violations": 0,
        },
        "latency_slos_are_local_development_only": True,
        "notice": "Performance results are bounded, synthetic, and hardware-specific; not production capacity evidence.",
    }


@router.get("/api/v1/performance/executions/{execution_id}")
def performance_execution(
    execution_id: str, actor: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "evaluation:read", session, action="performance_read")
        item = session.scalar(
            select(PerformanceExecutionRecord).where(
                PerformanceExecutionRecord.execution_id == execution_id
            )
        )
    if item is None:
        raise HTTPException(status_code=404, detail="performance execution not found")
    return _safe_model(item)


@router.get("/api/v1/performance/executions/{execution_id}/metrics")
def performance_metrics(
    execution_id: str, actor: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "evaluation:read", session, action="performance_read")
        execution = session.scalar(
            select(PerformanceExecutionRecord).where(
                PerformanceExecutionRecord.execution_id == execution_id
            )
        )
        rows = list(
            session.scalars(
                select(PerformanceMetricRecord).where(
                    PerformanceMetricRecord.execution_id == execution_id
                )
            )
        )
    if execution is None:
        raise HTTPException(status_code=404, detail="performance execution not found")
    return {
        "items": [_safe_model(item) for item in rows],
        "notice": "N/A measurements are not inferred as passes.",
    }


@router.get("/api/v1/performance/executions/{execution_id}/slos")
def performance_slos(
    execution_id: str, actor: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "evaluation:read", session, action="performance_read")
        execution = session.scalar(
            select(PerformanceExecutionRecord).where(
                PerformanceExecutionRecord.execution_id == execution_id
            )
        )
        rows = list(
            session.scalars(
                select(PerformanceSLORecord).where(
                    PerformanceSLORecord.execution_id == execution_id
                )
            )
        )
    if execution is None:
        raise HTTPException(status_code=404, detail="performance execution not found")
    return {"items": [_safe_model(item) for item in rows]}


@router.get("/api/v1/performance/executions/{execution_id}/findings")
def performance_findings(
    execution_id: str, actor: ActorContext = Depends(development_actor)
) -> dict[str, Any]:
    with SessionLocal() as session:
        require_permission(actor, "evaluation:read", session, action="performance_read")
        execution = session.scalar(
            select(PerformanceExecutionRecord).where(
                PerformanceExecutionRecord.execution_id == execution_id
            )
        )
        rows = list(
            session.scalars(
                select(PerformanceFindingRecord).where(
                    PerformanceFindingRecord.execution_id == execution_id
                )
            )
        )
    if execution is None:
        raise HTTPException(status_code=404, detail="performance execution not found")
    return {"items": [_safe_model(item) for item in rows]}


@router.get("/api/v1/evaluations/{evaluation_id}")
def evaluation(evaluation_id: str) -> dict[str, object]:
    if evaluation_id == "cross-framework":
        return _cross_framework_output()
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
    return {
        "profiles": {
            name: value.get("metrics", {}) for name, value in output.get("profiles", {}).items()
        },
        "notice": "Synthetic development evaluation; not clinically validated.",
    }


@router.get("/api/v1/evaluations/{evaluation_id}/cases")
def evaluation_cases(evaluation_id: str, category: str | None = None) -> dict[str, object]:
    if evaluation_id == "cross-framework":
        output = _cross_framework_output()
        cases = output.get("cases", [])
        if category:
            cases = [case for case in cases if case.get("category") == category]
        return {
            "cases": cases,
            "notice": output.get("notice", "Synthetic development evaluation only."),
        }
    if evaluation_id not in {"phase2-5-bounded", "phase2-6-bounded"}:
        raise HTTPException(status_code=404, detail="evaluation not found")
    output = _evaluation_output()
    cases = [
        case for profile in output.get("profiles", {}).values() for case in profile.get("cases", [])
    ]
    if category:
        cases = [case for case in cases if case.get("category") == category]
    return {
        "cases": cases,
        "notice": "Case-level results are synthetic development evaluation only.",
    }


def _cross_framework_output() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[4]
    path = root / "evaluation_outputs/cross_framework_results.json"
    if not path.exists():
        return {
            "status": "not_available",
            "frameworks": {},
            "cases": [],
            "notice": "Synthetic development evaluation; not clinically validated or production performance.",
        }
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return (
        loaded if isinstance(loaded, dict) else {"status": "invalid", "frameworks": {}, "cases": []}
    )


@router.get("/api/v1/agents")
def agent_registry(_: ActorContext = Depends(development_actor)) -> dict[str, Any]:
    output = _cross_framework_output()
    scorecards = output.get("governance_scorecards", {})
    enriched = []
    for agent in framework_agents():
        item = agent.model_dump(mode="json")
        framework_key = "langgraph" if agent.framework == "LangGraph" else "crewai"
        card = scorecards.get(framework_key, {})
        item["governance_readiness"] = {
            "failed_gates": card.get("failed_gates", []),
            "evaluation_version": card.get("version"),
            "provenance_state": "pass"
            if "included_patient_required_criterion_provenance_coverage"
            not in card.get("failed_gates", [])
            else "remediation_required",
            "audit_state": "pass"
            if "required_audit_completeness" not in card.get("failed_gates", [])
            else "remediation_required",
            "recovery_state": agent.recovery,
        }
        enriched.append(item)
    return {
        "items": enriched,
        "notice": "Synthetic development registry; not clinically validated.",
    }


@router.get("/api/v1/framework-policy")
def framework_policy() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parents[4] / "evaluations/agents/framework_selection_policy.json"
    )
    if not path.exists():
        return {"status": "not_available", "frameworks": {}}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {"status": "invalid"}


@router.get("/api/v1/governance/thresholds")
def governance_thresholds() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[4] / "evaluations/agents/governance_thresholds.json"
    if not path.exists():
        return {"status": "not_available"}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {"status": "invalid"}


@router.get("/api/v1/governance/scorecard")
def governance_scorecard() -> dict[str, Any]:
    output = _cross_framework_output()
    return {
        "version": output.get("hardened_metric_version", "phase4d-governance-v1"),
        "frameworks": output.get("governance_scorecards", {}),
        "failed_gates": output.get("failed_gates", {}),
        "notice": "Internal synthetic development gates; not regulatory certification.",
    }


@router.get("/api/v1/retrieval-policy")
def retrieval_policy() -> dict[str, object]:
    path = Path(__file__).resolve().parents[4] / "evaluations/retrieval/retrieval_policy.json"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _local_planner_evaluation() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[4]
    path = root / "evaluation_outputs/phase3c_local_planner_comparison.json"
    if not path.exists():
        return {
            "status": "not_available",
            "models": {},
            "synthetic_development_evaluation": True,
            "not_clinically_validated": True,
        }
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {"status": "invalid", "models": {}}


@router.get("/api/v1/planner-policy")
def planner_policy(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    output = _local_planner_evaluation()
    policy = output.get("policy")
    if not isinstance(policy, dict):
        policy = select_policy({}, baseline=settings.local_planner_default_model)
        policy["status"] = "pending_phase3c_runtime_evaluation"
    return {
        "policy": policy,
        "evaluated_models": output.get("models", {}),
        "allowed_models": list(allowed_local_planner_models(settings)),
        "synthetic_development_evaluation": True,
        "not_clinically_validated": True,
        "not_production_performance": True,
    }


@router.get("/api/v1/evaluations/local-planners")
def local_planner_evaluations() -> dict[str, Any]:
    return _local_planner_evaluation()


@router.get("/api/v1/evaluations/local-planners/{evaluation_id}")
def local_planner_evaluation(evaluation_id: str) -> dict[str, Any]:
    output = _local_planner_evaluation()
    if (
        evaluation_id != output.get("evaluation_id", "phase3c-local-planners")
        or output.get("status") == "not_available"
    ):
        raise HTTPException(status_code=404, detail="local planner evaluation not found")
    return output


@router.post("/api/v1/clinical-search", response_model=ClinicalSearchResponse)
def clinical_search(
    request: ClinicalSearchRequest,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ClinicalSearchResponse:
    if any(item not in {"encounter", "patient-summary"} for item in request.document_types):
        raise HTTPException(status_code=422, detail="unsupported document type")
    if request.candidate_pool_size < request.top_k:
        raise HTTPException(
            status_code=422, detail="candidate_pool_size must be greater than or equal to top_k"
        )
    started = time.perf_counter()
    rerank_started = started
    metadata: dict[str, Any]
    reranker_metadata: dict[str, Any]
    try:
        dense_profile = request.retrieval_profile.replace("hybrid_", "")
        if request.retrieval_profile == "postgres_fts":
            items, first_latency = postgres_fts_search(
                session,
                request.dataset_id,
                request.query,
                request.candidate_pool_size,
                request.document_types,
                request.patient_id,
            )
            metadata = {
                "query_model_name": "none",
                "query_model_revision": "none",
                "document_model_name": "postgresql-fts",
                "document_model_revision": "database",
                "representation_strategy": "lexical clinical document text",
                "normalization_strategy": "none",
                "lexical_provider": "postgres_fts",
                "dense_provider": None,
                "fusion_method": None,
                "rrf_constant": None,
            }
        else:
            provider = provider_for(settings, dense_profile)
            provider.load()
            if request.retrieval_profile.startswith("hybrid_"):
                items, first_latency = hybrid_search(
                    session,
                    provider,
                    request.dataset_id,
                    request.query,
                    request.candidate_pool_size,
                    request.document_types,
                    request.patient_id,
                    settings.rrf_constant,
                )
                metadata = {
                    "query_model_name": provider.metadata.query_model_name,
                    "query_model_revision": provider.metadata.query_model_revision,
                    "document_model_name": provider.metadata.document_model_name,
                    "document_model_revision": provider.metadata.document_model_revision,
                    "representation_strategy": provider.metadata.pooling_strategy,
                    "normalization_strategy": provider.metadata.normalization_strategy,
                    "lexical_provider": "postgres_fts",
                    "dense_provider": dense_profile,
                    "fusion_method": "reciprocal_rank_fusion",
                    "rrf_constant": settings.rrf_constant,
                }
            else:
                items, first_latency = search(
                    session,
                    provider,
                    request.dataset_id,
                    request.query,
                    request.candidate_pool_size,
                    request.document_types,
                    request.patient_id,
                    request.minimum_score,
                )
                metadata = {
                    "query_model_name": provider.metadata.query_model_name,
                    "query_model_revision": provider.metadata.query_model_revision,
                    "document_model_name": provider.metadata.document_model_name,
                    "document_model_revision": provider.metadata.document_model_revision,
                    "representation_strategy": provider.metadata.pooling_strategy,
                    "normalization_strategy": provider.metadata.normalization_strategy,
                    "lexical_provider": None,
                    "dense_provider": dense_profile,
                    "fusion_method": None,
                    "rrf_constant": None,
                }
        if request.reranker == "medcpt_cross_encoder":
            reranker = get_reranker(
                settings.reranker_model,
                settings.reranker_model_revision,
                settings.embedding_device,
                settings.reranker_batch_size,
            )
            reranker.load()
            logits = reranker.rerank(request.query, items)
            for item, logit in zip(items, logits, strict=True):
                item["reranker_logit"] = logit
            items = sorted(
                items,
                key=lambda item: (-float(str(item["reranker_logit"])), str(item["document_id"])),
            )
            for index, item in enumerate(items, 1):
                item["initial_candidate_rank"] = item.get(
                    "initial_candidate_rank", item.get("rank", index)
                )
                item["reranked_rank"] = index
                item["final_rank"] = index
            reranker_metadata = {
                "reranker_model_name": reranker.metadata.model_name,
                "reranker_model_revision": reranker.metadata.model_revision,
            }
        else:
            reranker_metadata = {"reranker_model_name": None, "reranker_model_revision": None}
        items = items[: request.top_k]
        for index, item in enumerate(items, 1):
            item["rank"] = index
            item["final_rank"] = index
        reranking_latency = (time.perf_counter() - rerank_started) * 1000 - first_latency
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=503 if isinstance(exc, RuntimeError) else 422, detail=str(exc)
        ) from exc
    return ClinicalSearchResponse(
        query=request.query,
        dataset_id=request.dataset_id,
        result_count=len(items),
        model_name=metadata["document_model_name"],
        model_revision=metadata["document_model_revision"],
        search_latency_ms=(time.perf_counter() - started) * 1000,
        synthetic_data_notice="Synthetic Synthea data only.",
        score_notice="All retrieval and reranking scores are ranking signals, not clinical probabilities.",
        retrieval_profile=request.retrieval_profile,
        **metadata,
        reranker=request.reranker,
        candidate_pool_size=request.candidate_pool_size,
        first_stage_latency_ms=first_latency,
        reranking_latency_ms=max(0, reranking_latency),
        total_latency_ms=(time.perf_counter() - started) * 1000,
        **reranker_metadata,
        items=[ClinicalSearchResult.model_validate(item) for item in items],
    )


@router.get("/api/v1/models/clinical-embedding", response_model=ModelStatusResponse)
def clinical_embedding_status(
    settings: Settings = Depends(get_settings), session: Session = Depends(get_db)
) -> ModelStatusResponse:
    statuses: dict[str, object] = {
        "postgres_fts": {
            "configured": True,
            "loaded": True,
            "available": True,
            "device": "database",
            "limitations": ["Lexical baseline only."],
        }
    }
    for profile in ("medcpt", "bioclinicalbert"):
        provider = provider_for(settings, profile)
        statuses[profile] = provider.health()
    statuses["medcpt_cross_encoder"] = get_reranker(
        settings.reranker_model,
        settings.reranker_model_revision,
        settings.embedding_device,
        settings.reranker_batch_size,
    ).health()
    medcpt = provider_for(settings, "medcpt")
    last = last_indexing(session, medcpt.metadata.document_model_name)
    return ModelStatusResponse(
        providers=statuses,
        configured_model=medcpt.metadata.document_model_name,
        loaded_status="loaded" if medcpt.health()["loaded"] else "not_loaded",
        device=medcpt.metadata.device,
        embedding_dimension=medcpt.metadata.embedding_dimension,
        maximum_sequence_length=medcpt.metadata.document_max_length,
        pooling_method=medcpt.metadata.pooling_strategy,
        revision=medcpt.metadata.document_model_revision,
        last_successful_indexing_time=last.completed_at if last else None,
        current_limitations=[
            "Synthetic data only.",
            "Retrieval is not clinical validation.",
            "MedCPT was trained for PubMed-like biomedical text and may not generalize to all synthetic FHIR phrasing.",
        ],
    )


@router.get("/api/v1/indexing-runs")
def retrieval_indexing_runs(session: Session = Depends(get_db)) -> list[dict[str, object]]:
    return [
        {
            key: getattr(item, key)
            for key in (
                "id",
                "dataset_id",
                "model_name",
                "model_revision",
                "status",
                "requested_document_count",
                "processed_document_count",
                "created_embedding_count",
                "skipped_embedding_count",
                "failed_embedding_count",
                "batch_size",
                "device_type",
                "started_at",
                "completed_at",
                "failure_message",
            )
        }
        for item in session.scalars(
            select(IndexingRun).order_by(IndexingRun.started_at.desc())
        ).all()
    ]


@router.get("/api/v1/indexing-runs/{run_id}")
def retrieval_indexing_run(run_id: str, session: Session = Depends(get_db)) -> dict[str, object]:
    item = session.get(IndexingRun, run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="indexing run not found")
    return {
        key: getattr(item, key)
        for key in (
            "id",
            "dataset_id",
            "model_name",
            "model_revision",
            "status",
            "requested_document_count",
            "processed_document_count",
            "created_embedding_count",
            "skipped_embedding_count",
            "failed_embedding_count",
            "batch_size",
            "device_type",
            "started_at",
            "completed_at",
            "failure_message",
            "configuration",
        )
    }


@router.get("/api/v1/clinical-documents/{document_id}/provenance")
def clinical_document_provenance(
    document_id: str, session: Session = Depends(get_db)
) -> dict[str, object]:
    document = session.get(ClinicalDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="clinical document not found")
    chunks = session.scalars(
        select(ClinicalDocumentChunk)
        .where(ClinicalDocumentChunk.document_id == document_id)
        .order_by(ClinicalDocumentChunk.chunk_index)
    ).all()
    resources = session.scalars(
        select(FhirResource).where(
            FhirResource.dataset_id == document.dataset_id,
            FhirResource.fhir_id.in_(document.source_resource_ids),
        )
    ).all()
    return {
        "document": {
            "id": document.id,
            "dataset_id": document.dataset_id,
            "patient_id": document.patient_id,
            "encounter_id": document.encounter_id,
            "document_type": document.document_type,
            "document_version": document.document_version,
            "text_sha256": document.text_sha256,
            "builder_version": document.builder_version,
            "source_resource_ids": document.source_resource_ids,
        },
        "chunks": [
            {
                "id": c.id,
                "chunk_index": c.chunk_index,
                "token_start": c.token_start,
                "token_end": c.token_end,
                "token_count": c.token_count,
                "source_resource_ids": c.source_resource_ids,
            }
            for c in chunks
        ],
        "resources": [
            {
                "resource_type": r.resource_type,
                "fhir_id": r.fhir_id,
                "source_archive_name": r.source_archive_name,
                "source_member_path": r.source_member_path,
            }
            for r in resources
        ],
        "synthetic_data_notice": "Synthetic Synthea data only.",
    }


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
            implemented=[
                "Platform health and readiness reporting",
                "Foundation metadata API",
                "Bounded clinical retrieval",
                "Governed LangGraph cohort workflow with human approval",
                "Local Qwen structured planning with deterministic fallback",
                "Workflow Console, Approval Queue, Audit Explorer, and Agent Catalog",
                "Governed MCP read-only tool gateway with stdio and Streamable HTTP",
            ],
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
