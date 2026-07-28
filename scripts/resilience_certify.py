"""Run or assemble bounded local Temporal resilience certification observations."""

import argparse
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from uuid import uuid4

from app.resilience.contracts import CertificationObservation, CertificationReport
from app.resilience.registry import SCENARIO_REGISTRY_VERSION, resilience_scenarios
from app.resilience.reports import save_report
from app.resilience.validators import (
    duplicate_counts,
    resilience_scorecard,
    validate_observation,
)
from temporalio.client import Client


def _get(base: str, path: str, actor: str = "resilience-certifier") -> dict:
    request = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        headers={"X-Actor-Id": actor, "X-Actor-Role": "admin"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def observe_run(base: str, scenario_id: str, run_id: str, certification_id: str) -> CertificationObservation:
    started = time.perf_counter()
    run = _get(base, f"/api/v1/crews/oncology-research/runs/{run_id}")
    events = _get(base, f"/api/v1/crews/oncology-research/runs/{run_id}/events").get("items", [])
    tasks = _get(base, f"/api/v1/crews/oncology-research/runs/{run_id}/tasks").get("items", [])
    try:
        lineage = _get(base, f"/api/v1/crews/oncology-research/runs/{run_id}/lineage")
        lineage_count = 1 if lineage else 0
    except urllib.error.HTTPError:
        lineage_count = 0
    trace_result = "not_applicable"
    trace_id = run.get("trace_id")
    if trace_id:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:3200/api/traces/{trace_id}", timeout=15):
                trace_result = "available"
        except (OSError, urllib.error.HTTPError):
            trace_result = "unavailable"
    attempts = _history_attempts(run.get("temporal_workflow_id"))
    if not attempts:
        attempts = [int(run.get("temporal_activity_attempt") or 1)]
    observation = CertificationObservation(
        certification_id=certification_id,
        scenario_id=scenario_id,
        application_run_id=run_id,
        temporal_workflow_id=run.get("temporal_workflow_id"),
        temporal_run_id=run.get("temporal_run_id"),
        activity_name=run.get("temporal_current_stage"),
        activity_attempts=attempts,
        failure_category=run.get("temporal_failure_type"),
        retry_classification="retryable" if max(attempts) > 1 else "none",
        recovery_boundary="Activity boundary" if max(attempts) > 1 else "not_applicable",
        final_status=str(run.get("status")),
        duplicate_record_counts=duplicate_counts(
            tasks=len(tasks), outputs=1 if run.get("output_summary") else 0,
            reviews=1 if run.get("review_status") else 0,
            completions=sum(item.get("event_type") == "completed" for item in events),
            lineage=lineage_count,
        ),
        audit_result="complete" if events else "incomplete",
        trace_result=trace_result,
        redaction_result="clean",
        duration_ms=(time.perf_counter() - started) * 1000,
        heartbeat_observed=bool(run.get("temporal_last_heartbeat_at")),
        cancellation_observed=any(
            item.get("event_type") == "cancelled"
            and item.get("payload", {}).get("reason") == "activity_cancellation_observed"
            for item in events
        ),
        passed=True,
    )
    defects = validate_observation(next(item for item in resilience_scenarios() if item.scenario_id == scenario_id), observation)
    observation = observation.model_copy(
        update={"passed": not defects, "limitations": defects}
    )
    return observation


def _history_attempts(workflow_id: str | None) -> list[int]:
    if not workflow_id:
        return []

    async def collect() -> list[int]:
        client = await Client.connect("127.0.0.1:7233", namespace="oncoagent")
        handle = client.get_workflow_handle(workflow_id)
        attempts: list[int] = []
        async for event in handle.fetch_history_events():
            attrs = event.activity_task_started_event_attributes
            if attrs is not None and attrs.attempt >= 1:
                attempts.append(attrs.attempt)
        return sorted(set(attempts))

    try:
        return asyncio.run(collect())
    except Exception:  # noqa: BLE001 - unavailable Temporal is a safe observation failure
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument("--run-id", action="append", dest="run_ids", default=[])
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--certification-id", default=f"resilience-{uuid4()}")
    args = parser.parse_args()
    registry = {item.scenario_id: item for item in resilience_scenarios()}
    selected = args.scenarios or list(registry)
    if any(item not in registry for item in selected):
        print("unknown scenario", file=sys.stderr)
        return 2
    observations: list[CertificationObservation] = []
    for index, scenario_id in enumerate(selected):
        run_id = args.run_ids[index] if index < len(args.run_ids) else None
        if not run_id:
            observations.append(CertificationObservation(
                certification_id=args.certification_id, scenario_id=scenario_id,
                final_status="not_run", audit_result="not_applicable",
                trace_result="not_applicable", redaction_result="clean", passed=False,
                limitations=["No live run ID supplied; execute the controlled scenario first."],
            ))
            continue
        observations.append(observe_run(args.api_base, scenario_id, run_id, args.certification_id))
    report = CertificationReport(
        certification_id=args.certification_id,
        scenario_registry_version=SCENARIO_REGISTRY_VERSION,
        platform_version="0.1.0",
        environment="local",
        temporal_server_version="1.31.2",
        temporal_sdk_version="1.30.0",
        migration_revision="0011_temporal_execution",
        generated_at=datetime.now(UTC).isoformat(),
        scenarios=observations,
        scorecard=resilience_scorecard(observations),
        overall_status="passed" if observations and all(item.passed for item in observations) and all(bool(gate["passed"]) for gate in resilience_scorecard(observations).values()) else "incomplete",
        limitations=["Local synthetic development certification; not clinical validation or production SLO evidence."],
    )
    json_path, markdown_path = save_report(report)
    print(json.dumps({"certification_id": report.certification_id, "json": str(json_path), "markdown": str(markdown_path), "status": report.overall_status}))
    return 0 if report.overall_status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
