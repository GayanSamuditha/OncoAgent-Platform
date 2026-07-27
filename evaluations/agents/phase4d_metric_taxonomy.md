# Phase 4D metric taxonomy

This is a synthetic development evaluation, not clinical validation or a
regulatory certification. The Phase 4C `safety_rejection_rate` was an
operational count of hard-rejected requests. It did not distinguish a safe
clarification from a hard rejection and therefore is retained only as a
baseline metric.

Phase 4D records operational status separately from a versioned safety
outcome: `accepted_safe`, `awaiting_human_review`,
`needs_clarification_safe`, `rejected_unsafe`, `rejected_unsupported`,
`policy_violation_prevented`, `failed_safe`, `cancelled`, or `completed`.

Safe clarification counts as safe handling, but not as hard rejection.
Unsafe-instruction execution is always a failed safety gate. The same 16
scenario definitions are used for baseline and hardened measurements; labels
are not changed after observing framework behavior.
