"""Run the local Phase 5B Temporal worker."""

import asyncio

from app.temporal.worker import run

if __name__ == "__main__":
    asyncio.run(run())

