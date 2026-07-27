from collections.abc import Iterable
from statistics import median
from typing import Any

from .contracts import NormalizedEvaluationResult


def aggregate_results(results: Iterable[NormalizedEvaluationResult]) -> dict[str, Any]:
    grouped: dict[str, list[NormalizedEvaluationResult]] = {}
    for result in results:
        grouped.setdefault(result.framework, []).append(result)
    output: dict[str, Any] = {}
    for framework, items in grouped.items():
        latencies = sorted(item.total_latency_ms for item in items)
        output[framework] = {
            "scenario_count": len(items),
            "completion_rate": sum(
                item.final_status
                in {
                    "completed",
                    "awaiting_human_review",
                    "accepted",
                    "rejected",
                    "needs_clarification",
                }
                for item in items
            )
            / len(items),
            "expected_outcome_match": sum(item.expected_outcome_match for item in items)
            / len(items),
            "structured_output_validity": sum(
                item.error_category not in {"invalid_output", "validation_error"} for item in items
            )
            / len(items),
            "required_criterion_coverage": sum(item.required_criterion_coverage for item in items)
            / len(items),
            "evidence_provenance_coverage": sum(item.evidence_provenance_coverage for item in items)
            / len(items),
            "unsupported_claim_rate": sum(item.unsupported_claim_count > 0 for item in items)
            / len(items),
            "tool_policy_violation_rate": sum(item.tool_policy_violations > 0 for item in items)
            / len(items),
            "dataset_isolation_compliance": sum(
                item.dataset_policy_violations == 0 for item in items
            )
            / len(items),
            "human_review_enforcement": sum(
                (not item.approval_required) or item.approval_enforced for item in items
            )
            / len(items),
            "safety_rejection_rate": sum(item.safety_rejection for item in items) / len(items),
            "median_latency_ms": median(latencies) if latencies else 0,
            "p95_latency_ms": latencies[max(0, int(len(latencies) * 0.95) - 1)] if latencies else 0,
            "median_tool_call_count": median(item.tool_call_count for item in items)
            if items
            else 0,
            "fallback_rate": sum(item.fallback_count > 0 for item in items) / len(items),
            "audit_completeness": sum(item.audit_event_count > 0 for item in items) / len(items),
            "recovery_capabilities": sorted({item.process_recovery_capability for item in items}),
        }
    return output
