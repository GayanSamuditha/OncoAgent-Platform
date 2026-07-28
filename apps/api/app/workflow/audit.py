from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.workflow import (
    ApprovalDecision,
    ApprovalRequest,
    PolicyDecision,
    WorkflowCandidate,
    WorkflowEvent,
    WorkflowEvidence,
    WorkflowLineage,
    WorkflowRun,
    WorkflowStep,
    WorkflowToolCall,
)
from app.observability.telemetry import current_trace_context
from app.workflow.policy import validate_transition


def now() -> datetime:
    return datetime.now(UTC)


def event(
    run_id: str,
    correlation_id: str,
    event_type: str,
    node_name: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    trace_context = current_trace_context()
    with SessionLocal.begin() as session:
        session.add(
            WorkflowEvent(
                id=str(uuid4()),
                run_id=run_id,
                correlation_id=correlation_id,
                event_type=event_type,
                node_name=node_name,
                payload=payload or {},
                trace_id=trace_context["trace_id"],
                span_id=trace_context["span_id"],
            )
        )


def update_run(run_id: str, **values: Any) -> None:
    with SessionLocal.begin() as session:
        run = session.get(WorkflowRun, run_id)
        if run is not None:
            if "status" in values and values["status"] != run.status:
                validate_transition(run.status, values["status"])
            for key, value in values.items():
                setattr(run, key, value)


def step(
    run_id: str,
    node_name: str,
    status: str,
    input_summary: dict[str, Any] | None = None,
    output_summary: dict[str, Any] | None = None,
    error_category: str | None = None,
) -> None:
    with SessionLocal.begin() as session:
        session.add(
            WorkflowStep(
                id=str(uuid4()),
                run_id=run_id,
                node_name=node_name,
                status=status,
                input_summary=input_summary or {},
                output_summary=output_summary or {},
                error_category=error_category,
                completed_at=now() if status in {"completed", "failed"} else None,
            )
        )


def tool_call(
    run_id: str,
    name: str,
    version: str,
    status: str,
    arguments: dict[str, Any],
    result_summary: dict[str, Any] | None = None,
    fallback_reason: str | None = None,
    error_category: str | None = None,
) -> None:
    with SessionLocal.begin() as session:
        session.add(
            WorkflowToolCall(
                id=str(uuid4()),
                run_id=run_id,
                tool_name=name,
                tool_version=version,
                status=status,
                sanitized_arguments=arguments,
                result_summary=result_summary or {},
                fallback_reason=fallback_reason,
                error_category=error_category,
                completed_at=now() if status in {"success", "error", "timeout"} else None,
            )
        )


def policy(
    run_id: str, stage: str, decision: str, reason: str, details: dict[str, Any] | None = None
) -> None:
    with SessionLocal.begin() as session:
        session.add(
            PolicyDecision(
                id=str(uuid4()),
                run_id=run_id,
                stage=stage,
                decision=decision,
                reason=reason,
                details=details or {},
            )
        )


def lineage(
    run_id: str,
    entity_type: str,
    entity_id: str,
    entity_version: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    with SessionLocal.begin() as session:
        session.add(
            WorkflowLineage(
                id=str(uuid4()),
                run_id=run_id,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_version=entity_version,
                metadata_json=metadata or {},
            )
        )


def save_candidates(run_id: str, dataset_id: str, candidates: list[dict[str, Any]]) -> None:
    with SessionLocal.begin() as session:
        for rank, candidate in enumerate(candidates, 1):
            existing = session.scalar(
                select(WorkflowCandidate).where(
                    WorkflowCandidate.run_id == run_id,
                    WorkflowCandidate.patient_id == str(candidate["patient_id"]),
                )
            )
            if existing is None:
                session.add(
                    WorkflowCandidate(
                        id=str(uuid4()),
                        run_id=run_id,
                        dataset_id=dataset_id,
                        patient_id=str(candidate["patient_id"]),
                        document_ids=[str(candidate["document_id"])],
                        retrieval_provider=str(
                            candidate.get(
                                "retrieval_provider", candidate.get("model_name", "unknown")
                            )
                        ),
                        retrieval_rank=rank,
                        retrieval_score=float(candidate.get("similarity_score", 0.0)),
                        verification_status="pending",
                        included=False,
                    )
                )


def update_candidate_verification(
    run_id: str, verification: list[dict[str, Any]], included_patient_ids: list[str]
) -> None:
    """Persist the authoritative structured-verification outcome on candidates."""
    included = set(included_patient_ids)
    by_patient = {str(item["patient_id"]): item for item in verification}
    with SessionLocal.begin() as session:
        rows = session.scalars(
            select(WorkflowCandidate).where(WorkflowCandidate.run_id == run_id)
        ).all()
        for row in rows:
            result = by_patient.get(row.patient_id, {})
            statuses = [str(item.get("status")) for item in result.get("criteria", [])]
            row.included = row.patient_id in included
            row.verification_status = (
                "verified"
                if row.included
                else ("missing_data" if "missing_data" in statuses else "not_verified")
            )


def save_evidence(run_id: str, evidence_items: list[dict[str, Any]]) -> None:
    with SessionLocal.begin() as session:
        for item in evidence_items:
            session.add(
                WorkflowEvidence(
                    id=str(uuid4()),
                    run_id=run_id,
                    patient_id=item["patient_id"],
                    criterion_id=item["criterion_id"],
                    criterion_description=item["criterion_description"],
                    verification_status=item["verification_status"],
                    structured_value=item.get("structured_value", {}),
                    source_resource_type=item.get("source_resource_type"),
                    source_fhir_resource_id=item.get("source_fhir_resource_id"),
                    encounter_id=item.get("encounter_id"),
                    effective_timestamp=item.get("effective_timestamp"),
                    explanation=item["explanation"],
                    verification_tool=item["verification_tool"],
                    verification_tool_version=item["verification_tool_version"],
                    dataset_id=item["dataset_id"],
                )
            )


def create_approval(run_id: str, actor_id: str, payload: dict[str, Any]) -> str:
    with SessionLocal.begin() as session:
        existing = session.scalar(select(ApprovalRequest).where(ApprovalRequest.run_id == run_id))
        if existing is not None:
            return existing.id
        approval_id = str(uuid4())
        session.add(
            ApprovalRequest(
                id=approval_id,
                run_id=run_id,
                requested_by_actor_id=actor_id,
                status="pending",
                payload=payload,
            )
        )
        return approval_id


def get_approval(approval_id: str) -> ApprovalRequest | None:
    with SessionLocal() as session:
        return session.get(ApprovalRequest, approval_id)


def existing_decision(approval_id: str) -> ApprovalDecision | None:
    with SessionLocal() as session:
        return session.scalar(
            select(ApprovalDecision).where(ApprovalDecision.approval_id == approval_id)
        )
