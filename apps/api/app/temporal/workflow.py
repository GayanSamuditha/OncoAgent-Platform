"""Deterministic Temporal workflow coordinating the existing CrewAI sequence."""

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from app.temporal.contracts import (
        TemporalCrewWorkflowInput,
        TemporalReviewDecision,
        TemporalWorkflowStatus,
    )


@workflow.defn(name="CrewResearchWorkflow")
class CrewResearchWorkflow:
    def __init__(self) -> None:
        self._run_id = ""
        self._stage = "created"
        self._activity_attempt = 0
        self._review_decision: dict[str, Any] | None = None
        self._cancel_requested = False
        self._last_progress: dict[str, str] = {}

    @workflow.run
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        data = TemporalCrewWorkflowInput.model_validate(input_data)
        self._run_id = data.run_id
        retry_policy = RetryPolicy(
            maximum_attempts=2,
            non_retryable_error_types=[
                "safety_policy_rejection", "authorization_denied", "dataset_policy_denied",
                "invalid_request_schema", "invalid_task_contract", "final_brief_schema_violation",
                "review_authority_missing", "deterministic_governance_failure",
            ],
        )
        try:
            self._stage = "validate_request"
            request = await workflow.execute_activity(
                "validate_crew_request_activity", data.request, start_to_close_timeout=timedelta(seconds=60), retry_policy=retry_policy,
            )
            self._stage = "create_or_load_run"
            await workflow.execute_activity(
                "create_crew_run_activity", args=[data.run_id, data.temporal_workflow_id, data.correlation_id],
                start_to_close_timeout=timedelta(seconds=60), retry_policy=retry_policy,
            )
            self._stage = "execute_cohort_research"
            await workflow.execute_activity(
                "record_temporal_stage_activity", args=[data.run_id, self._stage, "started"],
                start_to_close_timeout=timedelta(seconds=60), retry_policy=retry_policy,
            )
            self._stage = "execute_crewai_pipeline"
            brief = await workflow.execute_activity(
                "execute_crewai_pipeline_activity", args=[data.run_id, request],
                start_to_close_timeout=timedelta(seconds=300), schedule_to_close_timeout=timedelta(seconds=900),
                heartbeat_timeout=timedelta(seconds=30), retry_policy=retry_policy,
            )
            for stage in ("execute_evidence_investigation", "execute_eligibility_review", "execute_research_brief"):
                self._stage = stage
                await workflow.execute_activity(
                    "record_temporal_stage_activity", args=[data.run_id, stage, "completed_by_sequential_crew"],
                    start_to_close_timeout=timedelta(seconds=60), retry_policy=retry_policy,
                )
            self._stage = "validate_final_brief"
            brief = await workflow.execute_activity(
                "validate_final_brief_activity", args=[data.run_id, brief],
                start_to_close_timeout=timedelta(seconds=60), retry_policy=retry_policy,
            )
            self._stage = "create_human_review"
            review_id = await workflow.execute_activity(
                "create_human_review_activity", data.run_id,
                start_to_close_timeout=timedelta(seconds=60), retry_policy=retry_policy,
            )
            self._stage = "waiting_for_human_review"
            await workflow.wait_condition(lambda: self._review_decision is not None or self._cancel_requested)
            decision = self._review_decision or {
                "decision": "cancel", "reviewer_id": "system", "reviewer_role": "admin", "comment": "workflow cancellation requested",
            }
            self._stage = "apply_review_decision"
            applied = await workflow.execute_activity(
                "apply_human_review_activity", args=[data.run_id, decision],
                start_to_close_timeout=timedelta(seconds=60), retry_policy=retry_policy,
            )
            if applied == "accept_for_synthetic_research":
                self._stage = "finalize_run"
                await workflow.execute_activity(
                    "finalize_crew_run_activity", data.run_id,
                    start_to_close_timeout=timedelta(seconds=60), retry_policy=retry_policy,
                )
            return {"run_id": data.run_id, "review_id": review_id, "status": applied, "brief": brief}
        except ActivityError as exc:
            cause = exc.cause
            if isinstance(cause, ApplicationError) and cause.type == "activity_cancelled":
                await workflow.execute_activity(
                    "persist_cancellation_activity", data.run_id,
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                return {"run_id": data.run_id, "status": "cancelled"}
            await workflow.execute_activity(
                "persist_failure_activity", args=[data.run_id, "activity_worker_failure", "Temporal Activity failed safely"],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            raise
        except ApplicationError as exc:
            if exc.type == "activity_cancelled":
                await workflow.execute_activity(
                    "persist_cancellation_activity", data.run_id,
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                return {"run_id": data.run_id, "status": "cancelled"}
            await workflow.execute_activity(
                "persist_failure_activity", args=[data.run_id, exc.type or "activity_failure", "Temporal Activity failed safely"],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            raise
        except Exception as exc:
            await workflow.execute_activity(
                "persist_failure_activity", args=[data.run_id, "activity_worker_failure", "Temporal workflow failed safely"],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            raise exc

    @workflow.signal(name="review_decision")
    async def review_decision(self, decision: dict[str, Any]) -> None:
        if self._review_decision is None:
            self._review_decision = TemporalReviewDecision.model_validate(decision).model_dump()

    @workflow.signal(name="cancel_run")
    async def cancel_run(self) -> None:
        self._cancel_requested = True

    @workflow.query(name="status")
    def status(self) -> dict[str, Any]:
        return TemporalWorkflowStatus(
            run_id=self._run_id,
            workflow_id=workflow.info().workflow_id,
            temporal_run_id=workflow.info().run_id,
            status="waiting_for_review" if self._stage == "waiting_for_human_review" else self._stage,
            current_stage=self._stage,
            activity_attempt=self._activity_attempt,
            waiting_for_review=self._stage == "waiting_for_human_review",
            review_decision_received=self._review_decision is not None,
            cancellation_requested=self._cancel_requested,
            last_safe_progress=self._last_progress,
        ).model_dump()
