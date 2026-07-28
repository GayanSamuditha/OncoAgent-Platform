"""Temporal Activity worker entry point."""

import asyncio
from collections.abc import Callable
from typing import Any, cast

from temporalio.client import Client
from temporalio.worker import Worker

from app.core.config import get_settings
from app.temporal.activities import ACTIVITIES
from app.temporal.workflow import CrewResearchWorkflow


async def run() -> None:
    settings = get_settings()
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[CrewResearchWorkflow],
        activities=cast(list[Callable[..., Any]], ACTIVITIES),
        max_concurrent_activities=1,
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run())
