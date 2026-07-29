"""Safe, correlation-scoped cleanup for local demo records."""

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AccessDecisionAudit,
    ApprovalDecision,
    ApprovalRequest,
    CrewAgent,
    CrewEvent,
    CrewLineage,
    CrewOutput,
    CrewReview,
    CrewRun,
    CrewTask,
    MCPRequest,
    PolicyDecision,
    WorkflowCandidate,
    WorkflowEvent,
    WorkflowEvidence,
    WorkflowLineage,
    WorkflowRun,
    WorkflowStep,
    WorkflowToolCall,
)
from app.security.audit_integrity import digest_for


def validate_demo_id(demo_id: str) -> str:
    value = demo_id.strip()
    if not value.startswith("client-demo-") or len(value) <= len("client-demo-"):
        raise ValueError("DEMO_ID must begin with client-demo-")
    return value


def _count(session: Session, model: Any, predicate: Any) -> int:
    return int(session.scalar(select(func.count()).select_from(model).where(predicate)) or 0)


def _correlated(column: Any, demo_id: str) -> Any:
    # Framework-specific child correlations are namespaced below the exact
    # demo ID (for example, client-demo-final-crewai).
    return or_(column == demo_id, column.like(f"{demo_id}-%"))


def demo_scope_counts(session: Session, demo_id: str) -> dict[str, int]:
    """Return only records whose application correlation is exactly demo_id."""
    demo_id = validate_demo_id(demo_id)
    workflow_ids = select(WorkflowRun.id).where(_correlated(WorkflowRun.correlation_id, demo_id))
    crew_ids = select(CrewRun.id).where(_correlated(CrewRun.correlation_id, demo_id))
    return {
        "workflow_runs": _count(
            session, WorkflowRun, _correlated(WorkflowRun.correlation_id, demo_id)
        ),
        "workflow_steps": _count(session, WorkflowStep, WorkflowStep.run_id.in_(workflow_ids)),
        "workflow_events": _count(session, WorkflowEvent, WorkflowEvent.run_id.in_(workflow_ids)),
        "workflow_tool_calls": _count(
            session, WorkflowToolCall, WorkflowToolCall.run_id.in_(workflow_ids)
        ),
        "workflow_candidates": _count(
            session, WorkflowCandidate, WorkflowCandidate.run_id.in_(workflow_ids)
        ),
        "workflow_evidence": _count(
            session, WorkflowEvidence, WorkflowEvidence.run_id.in_(workflow_ids)
        ),
        "workflow_approvals": _count(
            session, ApprovalRequest, ApprovalRequest.run_id.in_(workflow_ids)
        ),
        "workflow_approval_decisions": _count(
            session, ApprovalDecision, ApprovalDecision.run_id.in_(workflow_ids)
        ),
        "workflow_policy_decisions": _count(
            session, PolicyDecision, PolicyDecision.run_id.in_(workflow_ids)
        ),
        "workflow_lineage": _count(
            session, WorkflowLineage, WorkflowLineage.run_id.in_(workflow_ids)
        ),
        "crew_runs": _count(session, CrewRun, _correlated(CrewRun.correlation_id, demo_id)),
        "crew_agents": _count(session, CrewAgent, CrewAgent.crew_run_id.in_(crew_ids)),
        "crew_tasks": _count(session, CrewTask, CrewTask.crew_run_id.in_(crew_ids)),
        "crew_events": _count(session, CrewEvent, CrewEvent.crew_run_id.in_(crew_ids)),
        "crew_outputs": _count(session, CrewOutput, CrewOutput.crew_run_id.in_(crew_ids)),
        "crew_reviews": _count(session, CrewReview, CrewReview.crew_run_id.in_(crew_ids)),
        "crew_lineage": _count(session, CrewLineage, CrewLineage.crew_run_id.in_(crew_ids)),
        "mcp_requests": _count(
            session, MCPRequest, _correlated(MCPRequest.correlation_id, demo_id)
        ),
    }


def reset_demo_records(session: Session, demo_id: str) -> dict[str, int]:
    """Delete exactly one demo correlation inside the caller's transaction."""
    demo_id = validate_demo_id(demo_id)
    counts = demo_scope_counts(session, demo_id)
    workflow_ids = select(WorkflowRun.id).where(_correlated(WorkflowRun.correlation_id, demo_id))
    crew_ids = select(CrewRun.id).where(_correlated(CrewRun.correlation_id, demo_id))

    # Delete children explicitly so this remains correct even when a local
    # database was created without PostgreSQL's FK cascade enforcement.
    child_deletes = (
        (WorkflowStep, WorkflowStep.run_id.in_(workflow_ids)),
        (WorkflowEvent, WorkflowEvent.run_id.in_(workflow_ids)),
        (WorkflowToolCall, WorkflowToolCall.run_id.in_(workflow_ids)),
        (WorkflowCandidate, WorkflowCandidate.run_id.in_(workflow_ids)),
        (WorkflowEvidence, WorkflowEvidence.run_id.in_(workflow_ids)),
        (ApprovalDecision, ApprovalDecision.run_id.in_(workflow_ids)),
        (ApprovalRequest, ApprovalRequest.run_id.in_(workflow_ids)),
        (PolicyDecision, PolicyDecision.run_id.in_(workflow_ids)),
        (WorkflowLineage, WorkflowLineage.run_id.in_(workflow_ids)),
        (CrewAgent, CrewAgent.crew_run_id.in_(crew_ids)),
        (CrewTask, CrewTask.crew_run_id.in_(crew_ids)),
        (CrewEvent, CrewEvent.crew_run_id.in_(crew_ids)),
        (CrewOutput, CrewOutput.crew_run_id.in_(crew_ids)),
        (CrewReview, CrewReview.crew_run_id.in_(crew_ids)),
        (CrewLineage, CrewLineage.crew_run_id.in_(crew_ids)),
    )
    for model, predicate in child_deletes:
        session.execute(delete(model).where(predicate))
    session.execute(delete(WorkflowRun).where(_correlated(WorkflowRun.correlation_id, demo_id)))
    session.execute(delete(CrewRun).where(_correlated(CrewRun.correlation_id, demo_id)))
    session.execute(delete(MCPRequest).where(_correlated(MCPRequest.correlation_id, demo_id)))

    # Keep a tamper-evident reset record. It is intentionally not part of the
    # deletion scope and contains counts only, never patient or credential data.
    audit = AccessDecisionAudit(
        id=str(uuid4()),
        actor_id=None,
        action="demo_reset",
        resource_type="demo",
        resource_id=demo_id,
        decision="allow",
        reason_code="explicit_demo_reset_confirmation",
        correlation_id=demo_id,
        details={"deleted_record_counts": dict(counts)},
        integrity_version="sha256-chain-v1",
    )
    previous = session.scalar(
        select(AccessDecisionAudit)
        .where(AccessDecisionAudit.canonical_digest.is_not(None))
        .order_by(AccessDecisionAudit.created_at.desc(), AccessDecisionAudit.id.desc())
    )
    audit.previous_digest = previous.canonical_digest if previous else None
    session.add(audit)
    session.flush()
    audit.canonical_digest = digest_for(audit)
    return counts


def sanitized_counts(counts: Mapping[str, int]) -> dict[str, int]:
    return {str(key): int(value) for key, value in counts.items()}
