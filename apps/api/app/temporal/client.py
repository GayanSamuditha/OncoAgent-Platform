"""Small application boundary for Temporal client operations."""

import asyncio
from datetime import timedelta
from typing import Any

from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from app.core.config import Settings
from app.temporal.contracts import TemporalCrewWorkflowInput
from app.temporal.workflow import CrewResearchWorkflow


class TemporalUnavailable(RuntimeError):
    """Temporal infrastructure is unavailable; legacy mode must not be implicit."""


async def connect(settings: Settings) -> Client:
    try:
        return await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    except Exception as exc:
        raise TemporalUnavailable("Temporal service is unavailable") from exc


async def start_workflow(settings: Settings, input_data: TemporalCrewWorkflowInput) -> dict[str, str]:
    client = await connect(settings)
    workflow_id = input_data.temporal_workflow_id
    try:
        handle = await client.start_workflow(
            CrewResearchWorkflow.run,
            input_data.model_dump(mode="json"),
            id=workflow_id,
            task_queue=settings.temporal_task_queue,
            execution_timeout=timedelta(seconds=settings.temporal_workflow_execution_timeout_seconds),
        )
    except WorkflowAlreadyStartedError:
        handle = client.get_workflow_handle(workflow_id)
    return {"workflow_id": handle.id, "run_id": handle.result_run_id or ""}


async def signal_review(settings: Settings, workflow_id: str, decision: dict[str, Any]) -> None:
    client = await connect(settings)
    await client.get_workflow_handle(workflow_id).signal(CrewResearchWorkflow.review_decision, decision)


async def signal_cancel(settings: Settings, workflow_id: str) -> None:
    client = await connect(settings)
    await client.get_workflow_handle(workflow_id).signal(CrewResearchWorkflow.cancel_run)


async def query_status(settings: Settings, workflow_id: str) -> dict[str, Any]:
    client = await connect(settings)
    return await client.get_workflow_handle(workflow_id).query(CrewResearchWorkflow.status)


def run_sync(operation: Any, *args: Any) -> Any:
    try:
        return asyncio.run(operation(*args))
    except TemporalUnavailable:
        raise
    except Exception as exc:
        raise TemporalUnavailable("Temporal operation failed safely") from exc
