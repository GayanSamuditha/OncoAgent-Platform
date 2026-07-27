"""Run the source-controlled CrewAI scenarios against the local API.

Outputs are deliberately written below ignored evaluation_outputs/.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import uuid
from pathlib import Path
from typing import Any

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation-file", default="evaluations/crewai/phase4b_cases.json")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default="llama3.2:3b")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--case-ids", default="")
    parser.add_argument("--output", default="evaluation_outputs/crewai/phase4b_llama.json")
    args = parser.parse_args()
    cases = json.loads(Path(args.evaluation_file).read_text())
    if args.case_ids:
        wanted = set(args.case_ids.split(","))
        cases = [case for case in cases if case["case_id"] in wanted]
    if args.limit:
        cases = cases[: args.limit]
    client = httpx.Client(timeout=20)
    headers = {"X-Actor-Id": "crewai-evaluator", "X-Actor-Role": "researcher"}
    results: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        payload = {
            "dataset_id": case["dataset_id"],
            "research_question": case["request"],
            "structured_criteria": case["criteria"],
            "maximum_candidates": 10,
            "retrieval_profile": "medcpt",
            "model_profile": args.model,
            "actor_context": {"actor_id": "crewai-evaluator", "actor_role": "researcher"},
            "correlation_id": str(uuid.uuid4()),
            "idempotency_key": f"phase4b-{args.model}-{case['case_id']}-{uuid.uuid4().hex[:8]}",
        }
        response = client.post(
            f"{args.base_url}/api/v1/crews/oncology-research/runs",
            headers=headers,
            json=payload,
        )
        record: dict[str, Any] = {
            "scenario_id": case["case_id"],
            "category": case["category"],
            "expected_outcome": case["expected_outcome"],
            "model": args.model,
            "http_status": response.status_code,
            "started_at": time.time(),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        if response.is_success:
            run = response.json()
            run_id = run["run_id"]
            record["run_id"] = run_id
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline:
                detail = client.get(
                    f"{args.base_url}/api/v1/crews/oncology-research/runs/{run_id}",
                    headers=headers,
                ).json()
                if detail["status"] in {
                    "awaiting_human_review",
                    "failed",
                    "cancelled",
                    "accepted",
                    "rejected",
                }:
                    break
                time.sleep(0.5)
            record["status"] = detail["status"]
            record["current_task"] = detail.get("current_task")
            events = client.get(
                f"{args.base_url}/api/v1/crews/oncology-research/runs/{run_id}/events",
                headers=headers,
            ).json()
            output_response = client.get(
                f"{args.base_url}/api/v1/crews/oncology-research/runs/{run_id}/output",
                headers=headers,
            )
            record["events"] = events.get("items", events if isinstance(events, list) else [])
            record["output_status"] = output_response.status_code
            if output_response.is_success:
                output = output_response.json()
                record["output"] = output
                brief = output.get("output", output)
                record["provenance_coverage"] = brief.get("provenance_summary", {})
                record["review_required"] = brief.get("review_status") == "awaiting_human_review"
            record["mcp_request_count"] = sum(
                1 for event in record["events"] if event.get("event_type") == "awaiting_human_review"
            )
            # Evaluation review decisions are explicit and separate from run execution.
            if record["status"] == "awaiting_human_review":
                review_response = client.post(
                    f"{args.base_url}/api/v1/crews/oncology-research/runs/{run_id}/review",
                    headers={"X-Actor-Id": "crewai-evaluator-reviewer", "X-Actor-Role": "reviewer"},
                    json={"decision": "reject", "comment": "Evaluation run closed safely."},
                )
                record["evaluation_review_status"] = review_response.status_code
        else:
            record["status"] = "rejected"
            try:
                record["error"] = response.json().get("detail", "safe rejection")
            except ValueError:
                record["error"] = "safe rejection"
        record["matches_expected"] = (
            record["status"] == case["expected_outcome"]
            or (case["expected_outcome"] == "rejected" and record["http_status"] in {400, 403, 422})
        )
        record["total_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        results.append(record)
        print(json.dumps({k: record.get(k) for k in ("scenario_id", "status", "http_status", "matches_expected")}))
    statuses = [str(item.get("status")) for item in results]
    latencies = [float(item["total_latency_ms"]) for item in results]
    safety = [item for item in results if item["category"] == "safety"]
    metrics = {
        "scenario_count": len(results),
        "completion_rate": sum(item["status"] in {"awaiting_human_review", "accepted", "rejected"} for item in results) / len(results),
        "expected_outcome_match_rate": sum(item["matches_expected"] for item in results) / len(results),
        "safety_rejection_rate": sum(item["matches_expected"] for item in safety) / len(safety) if safety else 0,
        "human_review_requirement_rate": sum(item.get("review_required", False) for item in results) / len(results),
        "median_total_latency_ms": statistics.median(latencies) if latencies else 0,
        "p95_total_latency_ms": sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] if latencies else 0,
        "statuses": {status: statuses.count(status) for status in sorted(set(statuses))},
    }
    output = {"label": "synthetic development evaluation; not clinically validated; not production performance", "model": args.model, "metrics": metrics, "results": results}
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
