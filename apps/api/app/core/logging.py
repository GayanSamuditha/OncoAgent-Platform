import logging
import sys
from collections.abc import MutableMapping
from typing import Any, cast

import structlog

from app.observability.telemetry import current_trace_context


def _trace_context(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    context = current_trace_context()
    event_dict.setdefault("trace_id", context["trace_id"])
    event_dict.setdefault("span_id", context["span_id"])
    return event_dict


def configure_logging(log_level: str) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level.upper())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            cast(Any, _trace_context),
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, log_level.upper())),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
