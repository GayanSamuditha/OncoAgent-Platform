"""Run the local Phase 5B Temporal worker."""

import asyncio

from app.core.config import get_settings
from app.core.runtime_config import validate_runtime_settings
from app.temporal.worker import run

if __name__ == "__main__":
    issues = validate_runtime_settings(get_settings(), service="worker")
    if issues:
        details = "; ".join(f"{item.field}: {item.reason}" for item in issues)
        raise SystemExit("invalid worker configuration: " + details)
    asyncio.run(run())
