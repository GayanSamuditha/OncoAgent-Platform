"""Temporal Activities. All side effects remain outside deterministic workflow code."""

import asyncio
import time
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from crewai_client.mcp_client import MCPGatewayClient
from crewai_client.schemas import CrewRunRequest, SyntheticResearchBrief
from crewai_client.service import CrewExecutionService
from crewai_client.validation import validate_brief
from temporalio import activity

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.crewai import CrewEvent, CrewLineage, CrewOutput, CrewReview, CrewRun, CrewTask
from app.models.mcp import MCPRequest
from app.observability.metrics import (
    CREW_FRAMEWORK,
    CREW_INTERRUPTS,
    ORPHAN_MCP,
    PERFORMANCE_CANCELLATION_LATENCY,
    PERFORMANCE_RECOVERY_TIME,
    PERFORMANCE_RETRY_BUDGET,
    TEMPORAL_RETRIES,
    WORKER_SERVICE,
    observe,
    observe_crew_outcome,
    observe_crew_task,
    observe_unsafe_prevention,
    observe_validation_failure,
)
from app.observability.telemetry import current_trace_context
from app.temporal.errors import application_failure
from app.temporal.fault_injection import configured_fault, safe_progress


def _heartbeat(stage: str, progress: str, task_index: int = 0) -> None:
    activity.heartbeat(safe_progress(stage, progress, task_index))


def _cancel_requested(run_id: str) -> bool:
    with SessionLocal() as session:
        run = session.get(CrewRun, run_id)
        return bool(run and run.status in {"cancellation_requested", "cancelled"})


def _persist_heartbeat(run_id: str, stage: str) -> None:
    with SessionLocal.begin() as session:
        run = session.get(CrewRun, run_id)
        if run:
            run.temporal_current_stage = stage
            run.temporal_last_heartbeat_at = datetime.now(UTC)


async def _development_controls(run_id: str, stage: str) -> None:
    settings = get_settings()
    attempt = activity.info().attempt
    boundary = datetime.now(UTC)
    recovery_seconds: float | None = None
    with SessionLocal.begin() as session:
        run = session.get(CrewRun, run_id)
        if run:
            previous_progress = run.temporal_last_heartbeat_at or run.updated_at or run.created_at
            run.temporal_activity_attempt = attempt
            if attempt > 1 and previous_progress is not None:
                recovery_seconds = max(0.0, (boundary - previous_progress).total_seconds())
    if PERFORMANCE_RETRY_BUDGET is not None:
        PERFORMANCE_RETRY_BUDGET.labels(operation=stage).set(
            max(0, settings.retry_budget_per_operation - max(0, attempt - 1))
        )
    if attempt > 1:
        observe(TEMPORAL_RETRIES, labels={"activity": stage})
        if recovery_seconds is not None:
            category = (
                "retryable_activity"
                if settings.temporal_dev_fault_category
                else "worker_interrupted"
            )
            observe(
                PERFORMANCE_RECOVERY_TIME,
                recovery_seconds,
                {"framework": CREW_FRAMEWORK, "failure_category": category},
            )
    fault = configured_fault(settings, stage, attempt)
    if fault:
        raise application_failure(fault, f"Development fault injection at {stage}")
    deadline = time.monotonic() + settings.temporal_dev_activity_delay_seconds
    while time.monotonic() < deadline:
        if _cancel_requested(run_id):
            raise application_failure("activity_cancelled", "Temporal cancellation observed at Activity boundary")
        _heartbeat(stage, "development_delay")
        _persist_heartbeat(run_id, stage)
        await asyncio.sleep(0.25)


async def _run_crewai_with_heartbeats(
    service: CrewExecutionService, parsed: CrewRunRequest, run_id: str
) -> SyntheticResearchBrief:
    execution = asyncio.create_task(asyncio.to_thread(service.run, parsed, run_id))
    while not execution.done():
        try:
            return await asyncio.wait_for(asyncio.shield(execution), timeout=10)
        except TimeoutError:
            _heartbeat("execute_crewai_pipeline", "running")
            _persist_heartbeat(run_id, "execute_crewai_pipeline")
    return await execution


@activity.defn(name="validate_crew_request_activity")
async def validate_crew_request_activity(request: dict[str, Any]) -> dict[str, Any]:
    from crewai_client.policy import validate_request

    parsed = CrewRunRequest.model_validate(request)
    settings = get_settings()
    allowed = {item for item in settings.crewai_mcp_dataset_ids.split(",") if item}
    try:
        validate_request(parsed, allowed)
    except ValueError as exc:
        observe_unsafe_prevention("request_validation")
        observe_validation_failure("request", WORKER_SERVICE)
        raise application_failure("safety_policy_rejection", "CrewAI request failed policy validation") from exc
    return cast(dict[str, Any], parsed.model_dump(mode="json"))


@activity.defn(name="create_crew_run_activity")
async def create_crew_run_activity(run_id: str, workflow_id: str, correlation_id: str) -> dict[str, str]:
    settings = get_settings()
    with SessionLocal.begin() as session:
        run = session.get(CrewRun, run_id)
        if run is None:
            raise application_failure("invalid_request_schema", "CrewAI run reservation was not found")
        run.temporal_workflow_id = workflow_id
        run.temporal_namespace = settings.temporal_namespace
        run.temporal_task_queue = settings.temporal_task_queue
        run.temporal_execution_mode = "temporal"
        run.temporal_execution_status = "running"
        run.temporal_correlation_id = correlation_id
        run.temporal_started_at = run.temporal_started_at or datetime.now(UTC)
        run.temporal_current_stage = "validate_request"
        run.status = "validating"
    return {"run_id": run_id, "workflow_id": workflow_id}


@activity.defn(name="record_temporal_stage_activity")
async def record_temporal_stage_activity(run_id: str, stage: str, progress: str) -> dict[str, str]:
    _heartbeat(stage, progress)
    with SessionLocal.begin() as session:
        run = session.get(CrewRun, run_id)
        if run is None:
            raise application_failure("invalid_request_schema", "CrewAI run was not found")
        run.temporal_current_stage = stage
        run.temporal_last_heartbeat_at = datetime.now(UTC)
        run.temporal_activity_attempt = activity.info().attempt
    return {"stage": stage, "progress": progress}


@activity.defn(name="execute_crewai_pipeline_activity")
async def execute_crewai_pipeline_activity(run_id: str, request: dict[str, Any]) -> dict[str, Any]:
    """Run the unchanged four-agent CrewAI sequence as one durable boundary."""

    parsed = CrewRunRequest.model_validate(request)
    settings = get_settings()
    _heartbeat("execute_crewai_pipeline", "started")
    await _development_controls(run_id, "execute_crewai_pipeline")
    client = MCPGatewayClient(
        settings.crewai_mcp_url,
        settings.crewai_mcp_client_id,
        settings.crewai_mcp_token,
        settings.crewai_max_tool_calls_per_run,
        run_id,
    )
    service = CrewExecutionService(settings, client)
    try:
        # CrewAI's existing sequential runtime and MCP adapter are synchronous
        # boundaries that own their event loops. Keep the Activity async for
        # Temporal heartbeats, but run that unchanged boundary off-loop so its
        # asyncio.run() calls do not collide with Temporal's worker loop.
        brief = await _run_crewai_with_heartbeats(service, parsed, run_id)
        if _cancel_requested(run_id):
            raise application_failure("activity_cancelled", "Temporal cancellation observed after CrewAI execution")
        validate_brief(brief, run_id, parsed.dataset_id)
    except ValueError as exc:
        observe_validation_failure("brief", WORKER_SERVICE)
        raise application_failure("final_brief_schema_violation", "CrewAI output failed validation") from exc
    except Exception as exc:
        raise application_failure("activity_worker_failure", "CrewAI Activity failed safely") from exc
    _heartbeat("execute_crewai_pipeline", "completed", 4)
    now = datetime.now(UTC)
    task_durations = cast(
        dict[str, float], service.last_execution.get("task_durations_seconds", {})
    )
    task_statuses = cast(dict[str, str], service.last_execution.get("task_statuses", {}))
    created_output = False
    with SessionLocal.begin() as session:
        run = session.get(CrewRun, run_id)
        if run is None:
            raise application_failure("invalid_request_schema", "CrewAI run was not found")
        existing_output = session.query(CrewOutput).filter(CrewOutput.crew_run_id == run_id).first()
        if existing_output is None:
            created_output = True
            session.add(CrewOutput(
                id=str(uuid4()), crew_run_id=run_id, output_type="synthetic_research_brief",
                schema_version="phase4b-brief-v1", output_json=cast(dict[str, Any], brief.model_dump(mode="json")),
            ))
        for task in session.query(CrewTask).filter(CrewTask.crew_run_id == run_id).all():
            task.status = "completed"
            task.completed_at = task.completed_at or now
        run.output_summary = {
            "candidate_count": brief.candidate_count,
            "proposed_included_count": brief.proposed_included_count,
            "provenance_coverage": brief.provenance_summary,
        }
        run.status = "awaiting_human_review"
        run.temporal_current_stage = "create_human_review"
        run.temporal_last_heartbeat_at = now
        run.temporal_activity_attempt = activity.info().attempt
        run.temporal_execution_status = "awaiting_human_review"
        session.add(CrewLineage(
            id=str(uuid4()), crew_run_id=run_id, config_version="phase5b-v1",
            config_hash=service.config_hash(settings), mcp_protocol_version="2025-06-18",
            mcp_server_version=settings.app_version, mcp_request_ids=client.request_ids,
            mcp_request_context=client.request_context,
            tool_names=sorted({"search_clinical_documents", "build_patient_evidence"}),
            retrieval_lineage=brief.retrieval_summary,
            token_usage={"fallback": service.last_execution.get("used_fallback", False)},
        ))
        session.add(CrewEvent(
            id=str(uuid4()), crew_run_id=run_id, event_type="temporal_pipeline_completed",
            payload={"stage": "execute_crewai_pipeline", "activity_attempt": activity.info().attempt},
            **current_trace_context(),
        ))
    if created_output:
        for task_name, duration_seconds in task_durations.items():
            observe_crew_task(
                task_name,
                task_statuses.get(task_name, "failed"),
                duration_seconds,
            )
    with SessionLocal() as session:
        persisted_request_count = (
            session.query(MCPRequest)
            .filter(MCPRequest.id.in_(set(client.request_ids)))
            .count()
            if client.request_ids
            else 0
        )
    if ORPHAN_MCP is not None:
        ORPHAN_MCP.labels(service=WORKER_SERVICE).set(
            max(0, len(set(client.request_ids)) - persisted_request_count)
        )
    return cast(dict[str, Any], brief.model_dump(mode="json"))


@activity.defn(name="validate_final_brief_activity")
async def validate_final_brief_activity(run_id: str, brief: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = SyntheticResearchBrief.model_validate(brief)
        validate_brief(parsed, run_id, parsed.dataset_id)
    except ValueError as exc:
        observe_validation_failure("brief", WORKER_SERVICE)
        raise application_failure(
            "final_brief_schema_violation", "CrewAI output failed validation"
        ) from exc
    return cast(dict[str, Any], parsed.model_dump(mode="json"))


@activity.defn(name="create_human_review_activity")
async def create_human_review_activity(run_id: str) -> str:
    with SessionLocal.begin() as session:
        review = session.query(CrewReview).filter(CrewReview.crew_run_id == run_id).first()
        if review is None:
            review = CrewReview(id=str(uuid4()), crew_run_id=run_id, status="pending")
            session.add(review)
            session.flush()
            session.add(CrewEvent(
                id=str(uuid4()), crew_run_id=run_id, event_type="human_review_created",
                payload={"review_required": True}, **current_trace_context(),
            ))
        run = session.get(CrewRun, run_id)
        if run:
            run.status = "awaiting_human_review"
            run.temporal_execution_status = "waiting_for_review"
            run.temporal_current_stage = "wait_for_review_decision"
        review_id = review.id
    return review_id


@activity.defn(name="apply_human_review_activity")
async def apply_human_review_activity(run_id: str, decision: dict[str, Any]) -> str:
    outcome: str | None = None
    interruption = False
    cancellation_latency: float | None = None
    with SessionLocal.begin() as session:
        review = session.query(CrewReview).filter(CrewReview.crew_run_id == run_id).first()
        run = session.get(CrewRun, run_id)
        if review is None or run is None:
            raise application_failure("review_authority_missing", "Human review record is unavailable")
        if decision.get("reviewer_id") == run.actor_id or decision.get("reviewer_role") not in {"reviewer", "admin"}:
            raise application_failure("review_authority_missing", "Reviewer authority or separation policy failed")
        if review.status != "pending":
            if review.decision == decision.get("decision"):
                return str(review.decision)
            raise application_failure("deterministic_governance_failure", "Conflicting review decision")
        decision_time = datetime.now(UTC)
        if decision.get("decision") == "cancel":
            cancellation_latency = max(0.0, (decision_time - run.updated_at).total_seconds())
        review.status = "decided"
        review.reviewer_id = decision["reviewer_id"]
        review.reviewer_role = decision["reviewer_role"]
        review.decision = decision["decision"]
        review.comment = decision.get("comment")
        review.decided_at = decision_time
        run.status = {"accept_for_synthetic_research": "accepted", "reject": "rejected", "request_changes": "awaiting_human_review", "cancel": "cancelled"}[review.decision]
        run.temporal_execution_status = run.status
        run.temporal_current_stage = "apply_review_decision"
        outcome = {
            "accept_for_synthetic_research": "accepted",
            "reject": "rejected",
            "request_changes": "changes_requested",
            "cancel": "cancelled",
        }[review.decision]
        interruption = review.decision == "cancel"
        session.add(CrewEvent(
            id=str(uuid4()), crew_run_id=run_id, event_type="review_decided",
            payload={"decision": review.decision, "reviewer_role": review.reviewer_role},
            **current_trace_context(),
        ))
        applied_decision = str(review.decision)
    if outcome is not None:
        observe_crew_outcome(outcome)
    if interruption:
        observe(CREW_INTERRUPTS, labels={"service": WORKER_SERVICE})
        if cancellation_latency is not None:
            observe(
                PERFORMANCE_CANCELLATION_LATENCY,
                cancellation_latency,
                {"framework": CREW_FRAMEWORK},
            )
    return applied_decision


@activity.defn(name="finalize_crew_run_activity")
async def finalize_crew_run_activity(run_id: str) -> str:
    with SessionLocal.begin() as session:
        run = session.get(CrewRun, run_id)
        if run is None:
            raise application_failure("invalid_request_schema", "CrewAI run was not found")
        run.temporal_current_stage = "finalize_run"
        run.temporal_execution_status = "completed"
        run.temporal_completed_at = datetime.now(UTC)
        session.add(CrewEvent(
            id=str(uuid4()), crew_run_id=run_id, event_type="completed",
            payload={"execution_mode": "temporal"}, **current_trace_context(),
        ))
    return "completed"


@activity.defn(name="persist_failure_activity")
async def persist_failure_activity(run_id: str, category: str, message: str) -> str:
    transitioned = False
    with SessionLocal.begin() as session:
        run = session.get(CrewRun, run_id)
        if run and run.status != "failed":
            transitioned = True
            run.status = "failed"
            run.error_category = category
            run.error_message = "Temporal execution failed safely"
            run.temporal_execution_status = "failed"
            run.temporal_failure_type = category
            run.temporal_failure_message_redacted = message[:200]
            run.temporal_completed_at = datetime.now(UTC)
    if transitioned:
        observe_crew_outcome("failed")
    return category


@activity.defn(name="persist_cancellation_activity")
async def persist_cancellation_activity(run_id: str) -> str:
    transitioned = False
    cancellation_latency: float | None = None
    with SessionLocal.begin() as session:
        run = session.get(CrewRun, run_id)
        if run and run.status != "cancelled":
            transitioned = True
            cancellation_time = datetime.now(UTC)
            cancellation_latency = max(0.0, (cancellation_time - run.updated_at).total_seconds())
            run.status = "cancelled"
            run.error_category = None
            run.temporal_execution_status = "cancelled"
            run.temporal_current_stage = "cancelled"
            run.temporal_completed_at = cancellation_time
            session.add(CrewEvent(
                id=str(uuid4()), crew_run_id=run_id, event_type="cancelled",
                payload={"reason": "activity_cancellation_observed"}, **current_trace_context(),
            ))
    if transitioned:
        observe_crew_outcome("cancelled")
        observe(CREW_INTERRUPTS, labels={"service": WORKER_SERVICE})
        if cancellation_latency is not None:
            observe(
                PERFORMANCE_CANCELLATION_LATENCY,
                cancellation_latency,
                {"framework": CREW_FRAMEWORK},
            )
    return "cancelled"


ACTIVITIES = [
    validate_crew_request_activity,
    create_crew_run_activity,
    record_temporal_stage_activity,
    execute_crewai_pipeline_activity,
    validate_final_brief_activity,
    create_human_review_activity,
    apply_human_review_activity,
    finalize_crew_run_activity,
    persist_failure_activity,
    persist_cancellation_activity,
]
