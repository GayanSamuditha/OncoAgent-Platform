"""Run equivalent scenarios through LangGraph and CrewAI sequentially."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import uuid
from pathlib import Path
from typing import Any

import httpx


def _criteria(case: dict[str, Any]) -> list[dict[str, Any]]:
    return case.get("criteria", [])


def _result(
    framework: str,
    case: dict[str, Any],
    run_id: str,
    response_status: int,
    status: str,
    started: float,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "evaluation_run_id": run_id,
        "scenario_id": case["scenario_id"],
        "category": case["scenario_id"],
        "framework": framework,
        "framework_version": "unknown",
        "agent_or_workflow_version": "unknown",
        "dataset_id": case["dataset_id"],
        "final_status": status,
        "expected_outcome_match": status == case["expected_outcome"]
        or (
            case["expected_outcome"] == "rejected"
            and response_status in {400, 403, 409, 422}
        ),
        "candidate_count": extra.pop("candidate_count", 0),
        "included_count": extra.pop("included_count", 0),
        "excluded_count": extra.pop("excluded_count", 0),
        "unresolved_count": extra.pop("unresolved_count", 0),
        "required_criterion_coverage": extra.pop("required_criterion_coverage", 0.0),
        "evidence_provenance_coverage": extra.pop("evidence_provenance_coverage", 0.0),
        "unsupported_claim_count": extra.pop("unsupported_claim_count", 0),
        "tool_policy_violations": 0,
        "dataset_policy_violations": 0,
        "approval_required": case["human_review_required"],
        "approval_enforced": status in {"awaiting_human_review", "accepted", "rejected"}
        if case["human_review_required"]
        else True,
        "safety_rejection": case["expected_outcome"] == "rejected"
        and response_status in {400, 403, 409, 422},
        "total_latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "model_latency_ms": None,
        "tool_call_count": extra.pop("tool_call_count", 0),
        "fallback_count": extra.pop("fallback_count", 0),
        "audit_event_count": extra.pop("audit_event_count", 0),
        "process_recovery_capability": "checkpoint_resume"
        if framework == "langgraph"
        else "process_interrupted_only",
        "error_category": extra.pop("error_category", None),
        "limitations": [
            "synthetic development evaluation",
            "not clinically validated",
            "not production performance",
        ],
        **extra,
    }


def run_framework(
    client: httpx.Client, base_url: str, framework: str, case: dict[str, Any]
) -> dict[str, Any]:
    started = time.perf_counter()
    actor = {
        "X-Actor-Id": f"cross-{framework}-researcher",
        "X-Actor-Role": "researcher",
    }
    if framework == "langgraph":
        payload = {
            "dataset_id": case["dataset_id"],
            "request": case["request"],
            "criteria": _criteria(case),
            "max_candidates": 20,
            "planner_provider": "deterministic",
        }
        response = client.post(f"{base_url}/api/v1/runs", headers=actor, json=payload)
        if not response.is_success:
            return _result(
                framework,
                case,
                str(uuid.uuid4()),
                response.status_code,
                "rejected",
                started,
                error_category="request_rejected",
            )
        body = response.json()
        run_id = body["run_id"]
        status = body.get("status", "unknown")
        if status == "awaiting_approval":
            status = "awaiting_human_review"
        events = (
            client.get(f"{base_url}/api/v1/runs/{run_id}/events", headers=actor)
            .json()
            .get("items", [])
        )
        evidence = (
            client.get(f"{base_url}/api/v1/runs/{run_id}/evidence", headers=actor)
            .json()
            .get("items", [])
        )
        candidates = (
            client.get(f"{base_url}/api/v1/runs/{run_id}/candidates", headers=actor)
            .json()
            .get("items", [])
        )
        return _result(
            framework,
            case,
            run_id,
            response.status_code,
            status,
            started,
            framework_version="langgraph",
            agent_or_workflow_version="phase3a-v1",
            candidate_count=len(candidates),
            evidence_provenance_coverage=(
                sum(bool(item.get("source_fhir_resource_id")) for item in evidence)
                / len(evidence)
                if evidence
                else 0
            ),
            tool_call_count=sum(
                "tool" in str(item.get("event_type", "")) for item in events
            ),
            audit_event_count=len(events),
        )
    payload = {
        "dataset_id": case["dataset_id"],
        "research_question": case["request"],
        "structured_criteria": _criteria(case),
        "maximum_candidates": 20,
        "retrieval_profile": "medcpt",
        "model_profile": "automatic",
        "actor_context": {
            "actor_id": "cross-crewai-researcher",
            "actor_role": "researcher",
        },
        "correlation_id": str(uuid.uuid4()),
    }
    response = client.post(
        f"{base_url}/api/v1/crews/oncology-research/runs", headers=actor, json=payload
    )
    if not response.is_success:
        return _result(
            framework,
            case,
            str(uuid.uuid4()),
            response.status_code,
            "rejected",
            started,
            error_category="request_rejected",
        )
    run_id = response.json()["run_id"]
    detail: dict[str, Any] = response.json()
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        detail = client.get(
            f"{base_url}/api/v1/crews/oncology-research/runs/{run_id}", headers=actor
        ).json()
        if detail.get("status") in {
            "awaiting_human_review",
            "failed",
            "cancelled",
            "rejected",
            "accepted",
        }:
            break
        time.sleep(0.5)
    events = (
        client.get(
            f"{base_url}/api/v1/crews/oncology-research/runs/{run_id}/events",
            headers=actor,
        )
        .json()
        .get("items", [])
    )
    output_response = client.get(
        f"{base_url}/api/v1/crews/oncology-research/runs/{run_id}/output", headers=actor
    )
    brief = (
        output_response.json().get("output", {}) if output_response.is_success else {}
    )
    return _result(
        framework,
        case,
        run_id,
        response.status_code,
        str(detail.get("status", "failed")),
        started,
        framework_version="1.15.7",
        agent_or_workflow_version="phase4b-v1",
        candidate_count=int(brief.get("candidate_count", 0)),
        included_count=int(brief.get("proposed_included_count", 0)),
        excluded_count=int(brief.get("proposed_excluded_count", 0)),
        unresolved_count=int(brief.get("unresolved_count", 0)),
        evidence_provenance_coverage=1.0 if brief.get("provenance_summary") else 0.0,
        tool_call_count=sum(
            "tool" in str(item.get("event_type", "")) for item in events
        ),
        fallback_count=sum(
            item.get("event_type") == "fallback_activated" for item in events
        ),
        audit_event_count=len(events),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--cases", default="evaluations/agents/cross_framework_cases.json"
    )
    parser.add_argument(
        "--output", default="evaluation_outputs/cross_framework_results.json"
    )
    args = parser.parse_args()
    cases = json.loads(Path(args.cases).read_text())
    results: list[dict[str, Any]] = []
    with httpx.Client(timeout=30) as client:
        for case in cases:
            for framework in ("langgraph", "crewai"):
                result = run_framework(client, args.base_url, framework, case)
                results.append(result)
                print(
                    json.dumps(
                        {
                            "framework": framework,
                            "scenario_id": case["scenario_id"],
                            "status": result["final_status"],
                            "match": result["expected_outcome_match"],
                        }
                    )
                )
                if (
                    framework == "crewai"
                    and result["final_status"] == "awaiting_human_review"
                ):
                    client.post(
                        f"{args.base_url}/api/v1/crews/oncology-research/runs/{result['evaluation_run_id']}/review",
                        headers={
                            "X-Actor-Id": "cross-reviewer",
                            "X-Actor-Role": "reviewer",
                        },
                        json={
                            "decision": "reject",
                            "comment": "Closed after synthetic evaluation.",
                        },
                    )
    framework_metrics: dict[str, Any] = {}
    for framework in ("langgraph", "crewai"):
        items = [item for item in results if item["framework"] == framework]
        latencies = sorted(item["total_latency_ms"] for item in items)
        framework_metrics[framework] = {
            "scenario_count": len(items),
            "completion_rate": sum(
                item["final_status"]
                in {
                    "awaiting_human_review",
                    "accepted",
                    "rejected",
                    "needs_clarification",
                }
                for item in items
            )
            / len(items),
            "expected_outcome_match": sum(
                item["expected_outcome_match"] for item in items
            )
            / len(items),
            "required_criterion_coverage": statistics.mean(
                item["required_criterion_coverage"] for item in items
            ),
            "evidence_provenance_coverage": statistics.mean(
                item["evidence_provenance_coverage"] for item in items
            ),
            "human_review_enforcement": sum(item["approval_enforced"] for item in items)
            / len(items),
            "safety_rejection_rate": sum(item["safety_rejection"] for item in items)
            / len(items),
            "median_latency_ms": statistics.median(latencies),
            "p95_latency_ms": latencies[max(0, int(len(latencies) * 0.95) - 1)],
            "median_tool_call_count": statistics.median(
                item["tool_call_count"] for item in items
            ),
            "fallback_rate": sum(item["fallback_count"] > 0 for item in items)
            / len(items),
            "audit_completeness": sum(item["audit_event_count"] > 0 for item in items)
            / len(items),
        }
    output = {
        "status": "completed",
        "scenario_count": len(cases),
        "frameworks": framework_metrics,
        "results": results,
        "notice": "Synthetic development evaluation; local hardware; not clinically validated or production performance.",
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
