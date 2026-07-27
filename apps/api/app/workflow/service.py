from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from sqlalchemy import select

from app.core.config import Settings
from app.db.session import SessionLocal
from app.models.workflow import (
    ApprovalRequest,
    WorkflowCandidate,
    WorkflowEvent,
    WorkflowEvidence,
    WorkflowRun,
    WorkflowToolCall,
)
from app.workflow.audit import event, update_run
from app.workflow.graph import build_graph
from app.workflow.schemas import ActorContext, RunCreateRequest


def _checkpointer_url(settings: Settings) -> str:
    return settings.database_url.replace("postgresql+psycopg://", "postgresql://")


@contextmanager
def checkpointer(settings: Settings) -> Iterator[PostgresSaver]:
    with PostgresSaver.from_conn_string(_checkpointer_url(settings)) as saver:
        saver.setup()
        yield saver


def invoke_run(run_id: str, settings: Settings, initial_state: dict[str, Any] | None = None, resume: dict[str, Any] | None = None) -> None:
    try:
        with checkpointer(settings) as saver:
            graph = build_graph(saver)
            config = {"configurable": {"thread_id": run_id}}
            if resume is None:
                graph.invoke(initial_state or {}, config)
            else:
                graph.invoke(Command(resume=resume), config)
    except Exception as exc:
        update_run(run_id, status="failed", current_node="fail_safely", errors=[f"{type(exc).__name__}: {exc}"], completed_at=datetime.now(UTC), final_result={"errors": [str(exc)], "synthetic_data_notice": "Synthetic Synthea data only."})
        event(run_id, run_id, "failed", "fail_safely", {"error_category": type(exc).__name__})
        raise


def create_run(request: RunCreateRequest, actor: ActorContext, settings: Settings) -> WorkflowRun:
    run_id = str(uuid4())
    with SessionLocal.begin() as session:
        run = WorkflowRun(id=run_id, thread_id=run_id, dataset_id=request.dataset_id, actor_id=actor.actor_id, actor_role=actor.role, original_request=request.request, structured_input={"criteria": [item.model_dump(mode="json") for item in request.criteria or []], "max_candidates": request.max_candidates}, retrieval_policy={}, status="created", current_node="intake", correlation_id=str(uuid4()), warnings=[], errors=[])
        session.add(run)
    initial = {"run_id": run_id, "thread_id": run_id, "actor_context": actor.model_dump(mode="json"), "dataset_id": request.dataset_id, "original_request": request.request, "structured_input": {"criteria": [item.model_dump(mode="json") for item in request.criteria or []], "max_candidates": request.max_candidates}, "retrieval_attempts": [], "retrieval_fallbacks": [], "candidate_patient_ids": [], "candidate_document_ids": [], "candidate_results": [], "verification_results": [], "evidence_items": [], "included_patient_ids": [], "excluded_patient_ids": [], "policy_decisions": [], "cancellation_requested": False, "warnings": [], "errors": [], "run_status": "created", "current_node": "intake", "created_at": datetime.now(UTC).isoformat(), "updated_at": datetime.now(UTC).isoformat()}
    invoke_run(run_id, settings, initial_state=initial)
    with SessionLocal() as session:
        result = session.get(WorkflowRun, run_id)
        if result is None:
            raise RuntimeError("workflow run disappeared after creation")
        return result


def get_run(run_id: str) -> WorkflowRun | None:
    with SessionLocal() as session:
        return session.get(WorkflowRun, run_id)


def resume_run(run: WorkflowRun, decision: dict[str, Any], settings: Settings) -> WorkflowRun:
    invoke_run(run.id, settings, resume=decision)
    refreshed = get_run(run.id)
    if refreshed is None:
        raise RuntimeError("workflow run not found after resume")
    return refreshed


def list_events(run_id: str) -> list[WorkflowEvent]:
    with SessionLocal() as session:
        return list(session.scalars(select(WorkflowEvent).where(WorkflowEvent.run_id == run_id).order_by(WorkflowEvent.created_at, WorkflowEvent.id)))


def list_evidence(run_id: str) -> list[WorkflowEvidence]:
    with SessionLocal() as session:
        return list(session.scalars(select(WorkflowEvidence).where(WorkflowEvidence.run_id == run_id).order_by(WorkflowEvidence.patient_id, WorkflowEvidence.criterion_id)))


def list_candidates(run_id: str) -> list[WorkflowCandidate]:
    with SessionLocal() as session:
        return list(session.scalars(select(WorkflowCandidate).where(WorkflowCandidate.run_id == run_id).order_by(WorkflowCandidate.retrieval_rank)))


def list_tools(run_id: str) -> list[WorkflowToolCall]:
    with SessionLocal() as session:
        return list(session.scalars(select(WorkflowToolCall).where(WorkflowToolCall.run_id == run_id).order_by(WorkflowToolCall.started_at)))


def get_approval_request(approval_id: str) -> ApprovalRequest | None:
    with SessionLocal() as session:
        return session.get(ApprovalRequest, approval_id)
