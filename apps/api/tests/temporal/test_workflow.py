import asyncio
import os

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.temporal.workflow import CrewResearchWorkflow

REQUEST = {
    "dataset_id": "synthea-eval-100",
    "research_question": "Find synthetic adults with hypertension",
    "structured_criteria": [
        {"criterion_type": "condition", "clinical_concept": "hypertension", "required": True}
    ],
    "maximum_candidates": 2,
    "retrieval_profile": "postgres_fts",
    "model_profile": "automatic",
    "actor_context": {"actor_id": "researcher", "actor_role": "researcher"},
}


@activity.defn(name="validate_crew_request_activity")
async def validate(request: dict) -> dict:
    return request


@activity.defn(name="create_crew_run_activity")
async def create(*_: str) -> dict[str, str]:
    return {"status": "created"}


@activity.defn(name="record_temporal_stage_activity")
async def record(*_: str) -> dict[str, str]:
    return {"status": "recorded"}


@activity.defn(name="execute_crewai_pipeline_activity")
async def execute(*_: object) -> dict:
    return {
        "run_id": "run-1",
        "dataset_id": "synthea-eval-100",
        "research_question": "Find synthetic adults with hypertension",
        "methods_summary": "Deterministic test output.",
        "retrieval_summary": {},
        "candidate_count": 0,
        "proposed_included_count": 0,
        "proposed_excluded_count": 0,
        "unresolved_count": 0,
        "patient_summaries": [],
        "evidence_limitations": [],
        "provenance_summary": {},
        "model_lineage": {},
        "mcp_lineage": {},
        "synthetic_data_notice": "Only synthetic Synthea data was used.",
        "clinical_validation_notice": "This result is not clinically validated.",
        "review_status": "awaiting_human_review",
    }


@activity.defn(name="validate_final_brief_activity")
async def validate_final(*args: object) -> dict:
    return args[-1]  # type: ignore[no-any-return]


@activity.defn(name="create_human_review_activity")
async def review(*_: str) -> str:
    return "review-1"


@activity.defn(name="apply_human_review_activity")
async def apply(_: str, decision: dict) -> str:
    return decision["decision"]


@activity.defn(name="finalize_crew_run_activity")
async def finalize(*_: str) -> str:
    return "completed"


@activity.defn(name="persist_failure_activity")
async def failure(*_: str) -> str:
    return "failed"


ACTIVITIES = [validate, create, record, execute, validate_final, review, apply, finalize, failure]


async def _run_test() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-temporal",
            workflows=[CrewResearchWorkflow],
            activities=ACTIVITIES,
        ):
            handle = await env.client.start_workflow(
                CrewResearchWorkflow.run,
                {
                    "run_id": "run-1",
                    "request": REQUEST,
                    "temporal_workflow_id": "crewai:run-1",
                    "correlation_id": "corr-1",
                },
                id="crewai:run-1",
                task_queue="test-temporal",
            )
            for _ in range(20):
                status = await handle.query(CrewResearchWorkflow.status)
                if status["waiting_for_review"]:
                    break
                await asyncio.sleep(0.05)
            assert status["waiting_for_review"] is True
            await handle.signal(
                CrewResearchWorkflow.review_decision,
                {
                    "decision": "accept_for_synthetic_research",
                    "reviewer_id": "reviewer",
                    "reviewer_role": "reviewer",
                    "comment": "accepted for development",
                },
            )
            result = await handle.result()
            assert result["status"] == "accept_for_synthetic_research"


def test_temporal_workflow_waits_for_and_applies_review() -> None:
    if os.getenv("RUN_TEMPORAL_TESTS") != "1":
        pytest.skip("Temporal test server is opt-in; set RUN_TEMPORAL_TESTS=1")
    asyncio.run(_run_test())
