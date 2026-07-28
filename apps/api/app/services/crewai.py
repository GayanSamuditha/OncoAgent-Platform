"""Persistence and bounded execution for the downstream CrewAI application."""

from datetime import UTC, datetime
from multiprocessing import Process
from typing import Any
from uuid import uuid4

from crewai_client.mcp_client import MCPGatewayClient
from crewai_client.schemas import CrewRunRequest
from crewai_client.service import CrewExecutionService

from app.db.session import SessionLocal
from app.models.crewai import (
    CrewAgent,
    CrewEvent,
    CrewLineage,
    CrewOutput,
    CrewReview,
    CrewRun,
    CrewTask,
)

_active_run: str | None = None
_worker_process: Process | None = None

ACTIVE_STATUSES = {
    "created",
    "validating",
    "running",
    "discovering_candidates",
    "collecting_evidence",
    "reviewing_evidence",
    "generating_brief",
}


def _event(
    session: Any,
    run_id: str,
    event_type: str,
    payload: dict[str, Any],
    task_name: str | None = None,
) -> None:
    session.add(
        CrewEvent(
            id=str(uuid4()),
            crew_run_id=run_id,
            event_type=event_type,
            task_name=task_name,
            payload=payload,
        )
    )


def create_run(request: CrewRunRequest, settings: Any) -> CrewRun:
    global _active_run, _worker_process
    with SessionLocal.begin() as session:
        if request.idempotency_key:
            existing = (
                session.query(CrewRun)
                .filter(CrewRun.idempotency_key == request.idempotency_key)
                .first()
            )
            if existing:
                return existing
        if _active_run:
            active = session.get(CrewRun, _active_run)
            if active and active.status in ACTIVE_STATUSES:
                raise RuntimeError(
                    "only one CrewAI run may execute at a time on the local development host"
                )
        run_id = str(uuid4())
        correlation_id = request.correlation_id or str(uuid4())
        model = (
            settings.crewai_default_model
            if request.model_profile == "automatic"
            else request.model_profile
        )
        run = CrewRun(
            id=run_id,
            correlation_id=correlation_id,
            dataset_id=request.dataset_id,
            actor_id=request.actor_context.actor_id,
            actor_role=request.actor_context.actor_role,
            mcp_client_id=settings.crewai_mcp_client_id,
            crew_name="OncologyResearchCrew",
            crew_version="phase4b-v1",
            crewai_version="1.15.7",
            process_type="sequential",
            model_tag=model,
            status="created",
            research_question=request.research_question,
            structured_criteria=[item.model_dump() for item in request.structured_criteria],
            sanitized_input={
                "dataset_id": request.dataset_id,
                "maximum_candidates": request.maximum_candidates,
                "retrieval_profile": request.retrieval_profile,
                "model_profile": request.model_profile,
            },
            idempotency_key=request.idempotency_key,
        )
        session.add(run)
        session.flush()
        for role, tools in (
            ("Cohort Researcher", ["search_clinical_documents"]),
            (
                "Structured Evidence Investigator",
                [
                    "get_patient_demographics",
                    "get_patient_conditions",
                    "get_patient_observations",
                    "get_patient_procedures",
                    "get_patient_medications",
                    "get_patient_diagnostic_reports",
                    "get_patient_encounters",
                    "verify_date_window",
                ],
            ),
            ("Eligibility Evidence Reviewer", ["build_patient_evidence", "verify_date_window"]),
            ("Research Brief Writer", []),
        ):
            session.add(
                CrewAgent(
                    id=str(uuid4()),
                    crew_run_id=run_id,
                    role=role,
                    version="phase4b-v1",
                    allowed_tools=tools,
                )
            )
        for task_name, role in (
            ("candidate_discovery", "Cohort Researcher"),
            ("structured_evidence_collection", "Structured Evidence Investigator"),
            ("eligibility_evidence_review", "Eligibility Evidence Reviewer"),
            ("research_brief_generation", "Research Brief Writer"),
        ):
            session.add(
                CrewTask(
                    id=str(uuid4()),
                    crew_run_id=run_id,
                    task_name=task_name,
                    task_version="phase4b-v1",
                    status="pending",
                    agent_role=role,
                )
            )
        _event(
            session,
            run_id,
            "created",
            {
                "synthetic_data_notice": "Synthetic Synthea data only.",
                "human_review_required": True,
            },
        )
        _active_run = run_id
    _worker_process = Process(target=_execute, args=(run_id, request, settings), daemon=True)
    _worker_process.start()
    with SessionLocal() as session:
        persisted = session.get(CrewRun, run_id)
        if persisted is None:
            raise RuntimeError("CrewAI run could not be persisted")
        return persisted


def _execute(run_id: str, request: CrewRunRequest, settings: Any) -> None:
    global _active_run
    started = datetime.now(UTC)
    with SessionLocal.begin() as session:
        run = session.get(CrewRun, run_id)
        if not run:
            return
        run.status, run.started_at, run.current_task = "validating", started, "candidate_discovery"
        task_rows = session.query(CrewTask).filter(CrewTask.crew_run_id == run_id).all()
        agent_rows = session.query(CrewAgent).filter(CrewAgent.crew_run_id == run_id).all()
        task_by_name = {task.task_name: task.id for task in task_rows}
        agent_by_role = {agent.role: agent.id for agent in agent_rows}
        first_task = session.query(CrewTask).filter(
            CrewTask.crew_run_id == run_id,
            CrewTask.task_name == "candidate_discovery",
        ).first()
        if first_task:
            first_task.status = "running"
        _event(session, run_id, "input_validated", {"process": "sequential"})
        _event(session, run_id, "crew_started", {"process": "sequential"})
        _event(session, run_id, "started", {"process": "sequential"})
        _event(
            session,
            run_id,
            "candidate_discovery_started",
            {
                "task_id": task_by_name["candidate_discovery"],
                "agent_id": agent_by_role["Cohort Researcher"],
                "dataset_id": run.dataset_id,
            },
            "candidate_discovery",
        )
    try:
        client = MCPGatewayClient(
            settings.crewai_mcp_url,
            settings.crewai_mcp_client_id,
            settings.crewai_mcp_token,
            settings.crewai_max_tool_calls_per_run,
            run_id,
        )
        service = CrewExecutionService(settings, client)
        with SessionLocal.begin() as session:
            run = session.get(CrewRun, run_id)
            if run:
                run.status = "running"
        brief = service.run(request, run_id)
        now = datetime.now(UTC)
        with SessionLocal.begin() as session:
            run = session.get(CrewRun, run_id)
            if not run:
                return
            if service.last_execution.get("used_fallback"):
                _event(
                    session,
                    run_id,
                    "fallback_activated",
                    {
                        "reason": service.last_execution.get("fallback_reason"),
                        "fallback_category": service.last_execution.get("fallback_category"),
                        "fallback": "deterministic",
                    },
                )
            _event(
                session,
                run_id,
                "candidate_discovery_completed",
                {
                    "task_id": task_by_name["candidate_discovery"],
                    "agent_id": agent_by_role["Cohort Researcher"],
                    "dataset_id": run.dataset_id,
                },
                "candidate_discovery",
            )
            for event_type, task_name, role in (
                ("evidence_collection_started", "structured_evidence_collection", "Structured Evidence Investigator"),
                ("evidence_collection_completed", "structured_evidence_collection", "Structured Evidence Investigator"),
                ("eligibility_review_started", "eligibility_evidence_review", "Eligibility Evidence Reviewer"),
                ("eligibility_review_completed", "eligibility_evidence_review", "Eligibility Evidence Reviewer"),
                ("brief_generation_started", "research_brief_generation", "Research Brief Writer"),
                ("brief_generation_completed", "research_brief_generation", "Research Brief Writer"),
            ):
                _event(
                    session,
                    run_id,
                    event_type,
                    {
                        "task_id": task_by_name[task_name],
                        "agent_id": agent_by_role[role],
                        "dataset_id": run.dataset_id,
                    },
                    task_name,
                )
            _event(session, run_id, "final_validation_completed", {"valid": True})
            run.status, run.current_task, run.completed_at, run.updated_at = (
                "awaiting_human_review",
                None,
                now,
                now,
            )
            for task in session.query(CrewTask).filter(CrewTask.crew_run_id == run_id).all():
                task.status = "completed"
                task.started_at = task.started_at or started
                task.completed_at = now
                task.latency_ms = max(0.0, (now - (task.started_at or started)).total_seconds() * 1000)
            run.output_summary = {
                "candidate_count": brief.candidate_count,
                "proposed_included_count": brief.proposed_included_count,
                "provenance_coverage": brief.provenance_summary,
            }
            session.add(
                CrewOutput(
                    id=str(uuid4()),
                    crew_run_id=run_id,
                    output_type="synthetic_research_brief",
                    schema_version="phase4b-brief-v1",
                    output_json=brief.model_dump(mode="json"),
                )
            )
            session.add(CrewReview(id=str(uuid4()), crew_run_id=run_id, status="pending"))
            session.add(
                CrewLineage(
                    id=str(uuid4()),
                    crew_run_id=run_id,
                    config_version="phase4b-v1",
                    config_hash=service.config_hash(settings),
                    mcp_protocol_version="2025-06-18",
                    mcp_server_version=settings.app_version,
                    mcp_request_ids=client.request_ids,
                    mcp_request_context=client.request_context,
                    tool_names=sorted({"search_clinical_documents", "build_patient_evidence"}),
                    retrieval_lineage=brief.retrieval_summary,
                    token_usage={
                        "fallback": service.last_execution.get("used_fallback", False),
                        "task_summaries": service.last_execution.get("task_summaries", {}),
                    },
                )
            )
            _event(session, run_id, "human_review_created", {"review_required": True})
            _event(
                session,
                run_id,
                "awaiting_human_review",
                {"mcp_request_count": len(client.request_ids), "review_required": True},
            )
    except Exception as exc:  # safe boundary; no internals returned
        with SessionLocal.begin() as session:
            run = session.get(CrewRun, run_id)
            if run:
                run.status, run.error_category, run.error_message, run.completed_at = (
                    "failed",
                    "internal_safe_failure",
                    "CrewAI run failed safely",
                    datetime.now(UTC),
                )
                _event(
                    session,
                    run_id,
                    "failed",
                    {
                        "error_category": "internal_safe_failure",
                        "error_type": type(exc).__name__,
                    },
                )
    finally:
        # The parent process owns the active-run guard. A child cannot mutate
        # it, so terminal status is always rechecked from PostgreSQL on the
        # next submission.
        _active_run = None


def cancel_run(run_id: str, actor_id: str) -> CrewRun | None:
    with SessionLocal.begin() as session:
        run = session.get(CrewRun, run_id)
        if run is None:
            return None
        if run.status not in ACTIVE_STATUSES:
            raise ValueError("CrewAI run is terminal or awaiting review")
        if run.actor_id != actor_id:
            raise PermissionError("researcher may cancel only their own run")
        run.status = "cancelled"
        _event(session, run_id, "cancelled", {"actor_id": actor_id})
        return run


def recover_incomplete_runs() -> int:
    """Mark in-flight local runs failed after a process restart.

    CrewAI execution is intentionally non-durable in this phase. Persisted
    records remain inspectable, but an interrupted model call is never
    resumed or reported as completed.
    """
    recovered = 0
    with SessionLocal.begin() as session:
        runs = session.query(CrewRun).filter(CrewRun.status.in_(ACTIVE_STATUSES)).all()
        for run in runs:
            run.status = "failed"
            run.error_category = "process_interrupted"
            run.error_message = "Local CrewAI execution was interrupted by process restart."
            run.completed_at = datetime.now(UTC)
            _event(session, run.id, "interrupted", {"error_category": "process_interrupted"})
            recovered += 1
    return recovered
