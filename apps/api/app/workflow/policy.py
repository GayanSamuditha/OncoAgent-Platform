"""Central workflow state-transition and execution policy rules."""

from typing import Final

TERMINAL_STATUSES: Final = {"completed", "rejected", "cancelled", "failed", "needs_clarification"}
ALLOWED_TRANSITIONS: Final[dict[str, set[str]]] = {
    "created": {"created", "planning", "failed"},
    "planning": {"planning", "validating_plan", "needs_clarification", "failed"},
    "validating_plan": {"validating_plan", "retrieving", "failed"},
    "retrieving": {"retrieving", "verifying", "failed"},
    "verifying": {"verifying", "validating_evidence", "failed"},
    "validating_evidence": {"validating_evidence", "awaiting_approval", "failed"},
    "awaiting_approval": {
        "awaiting_approval",
        "completed",
        "rejected",
        "cancelled",
        "needs_clarification",
        "failed",
    },
    "approved": {"approved", "completed", "failed"},
    "completed": {"completed"},
    "rejected": {"rejected"},
    "cancelled": {"cancelled"},
    "failed": {"failed"},
    "needs_clarification": {"needs_clarification"},
}


def validate_transition(current: str, requested: str) -> None:
    if requested not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid workflow state transition: {current} -> {requested}")
