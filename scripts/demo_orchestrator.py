"""Populate the client demo through real local APIs and existing runners.

This command never writes workflow, review, evaluation, or telemetry rows
directly. It only calls the platform's public local APIs and existing bounded
runner scripts. Runtime reports are written below ignored ``demo_outputs/``.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import uuid4

from app.core.config import Settings
from app.mcp_identity import MCPAuthError, configured_clients
from app.workflow.tools import build_tool_registry
from dotenv import dotenv_values

try:
    from scripts.demo_scenarios import (
        CREWAI_CRITERIA,
        CREWAI_QUESTION,
        DATASET_NAME,
        LANGGRAPH_CRITERIA,
        LANGGRAPH_QUESTION,
        SCENARIO_REGISTRY_VERSION,
    )
except ModuleNotFoundError:
    from demo_scenarios import (  # type: ignore[no-redef]
        CREWAI_CRITERIA,
        CREWAI_QUESTION,
        DATASET_NAME,
        LANGGRAPH_CRITERIA,
        LANGGRAPH_QUESTION,
        SCENARIO_REGISTRY_VERSION,
    )

ROOT = Path(__file__).resolve().parents[1]
API_BASE = os.getenv("DEMO_API_BASE", "http://127.0.0.1:8000")
WEB_BASE = os.getenv("DEMO_WEB_BASE", "http://127.0.0.1:3000")
OUTPUT_ROOT = ROOT / "demo_outputs"
DEMO_ENV = ROOT / ".env.demo"
DEMO_CLIENT_ID = "crewai-oncology-research"
DEMO_DATASET_ID = "6b15ce38-e12c-4482-866e-59d333952024"
DOCKER = "/Applications/Docker.app/Contents/Resources/bin/docker"
REQUIRED_MCP_TOOLS = {
    "search_clinical_documents",
    "get_patient_demographics",
    "get_patient_conditions",
    "get_patient_observations",
    "get_patient_procedures",
    "get_patient_medications",
    "get_patient_diagnostic_reports",
    "get_patient_encounters",
    "verify_date_window",
    "build_patient_evidence",
}


@dataclass
class DemoRun:
    demo_id: str
    dataset_id: str | None = None
    langgraph_run_id: str | None = None
    langgraph_approval_id: str | None = None
    crew_run_id: str | None = None
    crew_approval_id: str | None = None
    checks: list[dict[str, Any]] = field(default_factory=list)
    operations: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load_or_create(cls, demo_id: str) -> DemoRun:
        path = OUTPUT_ROOT / demo_id / "state.json"
        if path.exists():
            return cls(**json.loads(path.read_text(encoding="utf-8")))
        return cls(demo_id=demo_id)

    def save(self) -> None:
        path = OUTPUT_ROOT / self.demo_id
        path.mkdir(parents=True, exist_ok=True)
        (path / "state.json").write_text(
            json.dumps(self.__dict__, indent=2) + "\n", encoding="utf-8"
        )


class LocalApi:
    def __init__(self, actor: str, role: str) -> None:
        self.actor = actor
        self.role = role
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(
        self, path: str, method: str = "GET", body: dict[str, Any] | None = None
    ) -> tuple[int, Any]:
        headers = {
            "Accept": "application/json",
            "Origin": WEB_BASE,
            "X-Actor-Id": self.actor,
            "X-Actor-Role": self.role,
        }
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        request = Request(
            f"{API_BASE}{path}", data=data, headers=headers, method=method
        )
        try:
            with self.opener.open(request, timeout=180) as response:
                return response.status, json.loads(
                    response.read()
                ) if response.length != 0 else None
        except HTTPError as exc:
            try:
                payload = json.loads(exc.read())
            except (ValueError, json.JSONDecodeError):
                payload = {"detail": "redacted HTTP error"}
            return exc.code, payload
        except (URLError, TimeoutError) as exc:
            return 0, {"detail": type(exc).__name__}

    def login(self) -> None:
        status, payload = self.request(
            "/api/v1/auth/login", "POST", {"user_key": self.actor}
        )
        if status != 200:
            raise RuntimeError(
                f"{self.actor} login failed with status {status}: {payload.get('detail', 'unknown')}"
            )


def now_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def poll(
    api: LocalApi, path: str, terminal: set[str], timeout: int = 240
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, payload = api.request(path)
        if status >= 400 or not isinstance(payload, dict):
            raise RuntimeError(f"poll failed with status {status}")
        if str(payload.get("status")) in terminal:
            return payload
        time.sleep(2)
    raise TimeoutError(f"workflow did not reach a terminal state within {timeout}s")


def wait_temporal_review(api: LocalApi, run_id: str) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        status, payload = api.request(
            f"/api/v1/crews/oncology-research/runs/{run_id}/temporal"
        )
        workflow = (
            payload.get("workflow", {})
            if status == 200 and isinstance(payload, dict)
            else {}
        )
        if workflow.get("waiting_for_review") is True:
            return
        time.sleep(1)
    raise TimeoutError("Temporal workflow did not reach its durable review wait")


def record_operation(state: DemoRun, operation: dict[str, Any]) -> None:
    name = operation.get("name")
    state.operations = [item for item in state.operations if item.get("name") != name]
    state.operations.append(operation)


def correlation_id(state: DemoRun, suffix: str) -> str:
    """Derive a stable correlation within the existing varchar(36) contract."""
    base = (
        state.demo_id
        if state.demo_id.startswith("client-demo-")
        else f"client-demo-{state.demo_id}"
    )
    suffix_text = f"-{suffix}"
    return f"{base[: 36 - len(suffix_text)]}{suffix_text}"


def dataset_id(api: LocalApi) -> str:
    status, payload = api.request("/api/v1/datasets")
    if status != 200 or not isinstance(payload, list):
        raise RuntimeError("dataset list unavailable")
    for item in payload:
        if (
            isinstance(item, dict)
            and item.get("name") == DATASET_NAME
            and item.get("imported_patient_count") == 100
        ):
            return str(item["id"])
    raise RuntimeError("synthea-eval-100 with 100 patients was not found")


def populate_langgraph(state: DemoRun) -> None:
    researcher = LocalApi("researcher-console", "researcher")
    researcher.login()
    state.dataset_id = state.dataset_id or dataset_id(researcher)
    if state.langgraph_run_id:
        status, current = researcher.request(f"/api/v1/runs/{state.langgraph_run_id}")
        if status != 200:
            state.langgraph_run_id = None
        else:
            run = current
    if not state.langgraph_run_id:
        correlation = correlation_id(state, "langgraph")
        status, run = researcher.request(
            "/api/v1/runs",
            "POST",
            {
                "dataset_id": state.dataset_id,
                "request": LANGGRAPH_QUESTION,
                "criteria": LANGGRAPH_CRITERIA,
                "max_candidates": 10,
                "planner_provider": "deterministic",
                "correlation_id": correlation,
            },
        )
        if status not in {200, 201}:
            raise RuntimeError(f"LangGraph creation failed with status {status}")
        state.langgraph_run_id = str(run["run_id"])
        state.save()
    run = poll(
        researcher,
        f"/api/v1/runs/{state.langgraph_run_id}",
        {
            "awaiting_approval",
            "completed",
            "rejected",
            "failed",
            "needs_clarification",
            "cancelled",
        },
    )
    state.langgraph_approval_id = run.get("approval_id")
    if run.get("status") == "awaiting_approval" and state.langgraph_approval_id:
        self_status, _ = researcher.request(
            f"/api/v1/approvals/{state.langgraph_approval_id}/decision",
            "POST",
            {"decision": "approve", "comment": "Self-approval control probe."},
        )
        record_operation(
            state,
            {
                "name": "self_approval_denial",
                "status": "passed" if self_status == 403 else "failed",
                "http_status": self_status,
            },
        )
        reviewer = LocalApi("reviewer-console", "reviewer")
        reviewer.login()
        decision_status, _ = reviewer.request(
            f"/api/v1/approvals/{state.langgraph_approval_id}/decision",
            "POST",
            {
                "decision": "approve",
                "comment": "Approved for synthetic research after evidence review.",
            },
        )
        if decision_status >= 400:
            raise RuntimeError(
                f"reviewer approval failed with status {decision_status}"
            )
        run = poll(
            researcher,
            f"/api/v1/runs/{state.langgraph_run_id}",
            {"completed", "rejected", "failed", "needs_clarification", "cancelled"},
        )
    _, candidates = researcher.request(
        f"/api/v1/runs/{state.langgraph_run_id}/candidates"
    )
    _, evidence = researcher.request(f"/api/v1/runs/{state.langgraph_run_id}/evidence")
    candidate_rows = candidates.get("items", []) if isinstance(candidates, dict) else []
    evidence_rows = evidence.get("items", []) if isinstance(evidence, dict) else []
    included = [
        item
        for item in candidate_rows
        if isinstance(item, dict) and item.get("included") is True
    ]
    provenance = [
        item
        for item in evidence_rows
        if isinstance(item, dict) and item.get("source_fhir_resource_id")
    ]
    record_operation(
        state,
        {
            "name": "langgraph_research",
            "status": run.get("status"),
            "run_id": state.langgraph_run_id,
            "approval_id": state.langgraph_approval_id,
            "candidate_count": len(candidate_rows),
            "included_count": len(included),
            "excluded_count": len(candidate_rows) - len(included),
            "evidence_resource_count": len(provenance),
            "evidence_count": len(evidence_rows),
            "required_criterion_provenance_coverage": len(provenance)
            / len(evidence_rows)
            if evidence_rows
            else None,
            "reviewer_decision": "approved"
            if run.get("status") == "completed"
            else run.get("status"),
        },
    )
    state.save()


def populate_crewai(state: DemoRun) -> None:
    researcher = LocalApi("researcher-console", "researcher")
    researcher.login()
    state.dataset_id = state.dataset_id or dataset_id(researcher)
    crew_correlation = correlation_id(state, "crewai")
    status, payload = researcher.request(
        "/api/v1/crews/oncology-research/runs",
        "POST",
        {
            "dataset_id": state.dataset_id,
            "research_question": CREWAI_QUESTION,
            "structured_criteria": CREWAI_CRITERIA,
            "maximum_candidates": 10,
            "retrieval_profile": "postgres_fts",
            "model_profile": "automatic",
            "actor_context": {
                "actor_id": "researcher-console",
                "actor_role": "researcher",
            },
            "correlation_id": crew_correlation,
            "idempotency_key": crew_correlation,
        },
    )
    if status >= 400:
        raise RuntimeError(
            f"Temporal/CrewAI creation failed with status {status}: {payload.get('detail', 'unavailable')}"
        )
    state.crew_run_id = str(payload["run_id"])
    state.save()
    run = poll(
        researcher,
        f"/api/v1/crews/oncology-research/runs/{state.crew_run_id}",
        {"awaiting_human_review", "accepted", "rejected", "failed", "cancelled"},
    )
    state.crew_approval_id = run.get("approval_id") or run.get("review_id")
    if run.get("status") == "awaiting_human_review":
        wait_temporal_review(researcher, state.crew_run_id)
        self_status, _ = researcher.request(
            f"/api/v1/crews/oncology-research/runs/{state.crew_run_id}/review",
            "POST",
            {
                "decision": "accept_for_synthetic_research",
                "comment": "Self-approval control probe.",
            },
        )
        record_operation(
            state,
            {
                "name": "crewai_self_approval_denial",
                "status": "passed" if self_status == 403 else "failed",
                "http_status": self_status,
            },
        )
        reviewer = LocalApi("reviewer-console", "reviewer")
        reviewer.login()
        decision_status, _ = reviewer.request(
            f"/api/v1/crews/oncology-research/runs/{state.crew_run_id}/review",
            "POST",
            {
                "decision": "accept_for_synthetic_research",
                "comment": "Approved for synthetic research after evidence review.",
            },
        )
        if decision_status >= 400:
            raise RuntimeError(f"CrewAI review failed with status {decision_status}")
        run = poll(
            researcher,
            f"/api/v1/crews/oncology-research/runs/{state.crew_run_id}",
            {"accepted", "completed", "rejected", "failed", "cancelled"},
        )
    record_operation(
        state,
        {
            "name": "temporal_crewai_research",
            "status": run.get("status"),
            "run_id": state.crew_run_id,
        },
    )
    state.save()


def run_command(
    state: DemoRun, name: str, args: list[str], required: bool = False
) -> None:
    result = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    status = (
        "completed"
        if result.returncode == 0
        else "not_evaluable"
        if result.returncode == 2
        else "unavailable"
    )
    entry = {"name": name, "status": status, "exit_code": result.returncode}
    record_operation(state, entry)
    state.save()
    if required and result.returncode != 0:
        raise RuntimeError(f"{name} failed; see demo report for sanitized status")


def write_report(state: DemoRun) -> Path:
    output = OUTPUT_ROOT / state.demo_id
    output.mkdir(parents=True, exist_ok=True)
    try:
        application_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        application_commit = "unknown"
    screenshots = (
        sorted(
            str(path.relative_to(ROOT))
            for path in (output / "screenshots").glob("*.png")
        )
        if (output / "screenshots").exists()
        else []
    )
    langgraph_metrics = next(
        (item for item in state.operations if item.get("name") == "langgraph_research"),
        {},
    )
    crew_metrics: dict[str, Any] = {}
    observability: dict[str, Any] = {}
    page_summaries: dict[str, Any] = {}
    try:
        admin = LocalApi("admin-console", "administrator")
        admin.login()
        if state.crew_run_id:
            _, crew = admin.request(
                f"/api/v1/crews/oncology-research/runs/{state.crew_run_id}"
            )
            _, tasks = admin.request(
                f"/api/v1/crews/oncology-research/runs/{state.crew_run_id}/tasks"
            )
            _, lineage = admin.request(
                f"/api/v1/crews/oncology-research/runs/{state.crew_run_id}/lineage"
            )
            _, review = admin.request(
                f"/api/v1/crews/oncology-research/runs/{state.crew_run_id}/review"
            )
            if not isinstance(review, dict) or not review.get("id"):
                reviewer = LocalApi("reviewer-console", "reviewer")
                reviewer.login()
                _, review = reviewer.request(
                    f"/api/v1/crews/oncology-research/runs/{state.crew_run_id}/review"
                )
            crew_metrics = {
                key: crew.get(key)
                for key in (
                    "status",
                    "temporal_workflow_id",
                    "temporal_run_id",
                    "temporal_namespace",
                    "temporal_task_queue",
                    "temporal_activity_attempt",
                    "trace_id",
                    "correlation_id",
                )
            }
            crew_metrics.update(
                {
                    "task_statuses": [
                        item.get("status") for item in tasks.get("items", [])
                    ],
                    "mcp_request_count": len(lineage.get("mcp_request_ids", [])),
                    "review_id": review.get("id"),
                    "reviewer_identity": review.get("reviewer_id"),
                }
            )
        _, observability = admin.request("/api/v1/observability/metrics-summary")
        for name, path in (
            ("evaluations", "/api/v1/evaluations"),
            ("release_evaluations", "/api/v1/release-evaluations"),
            ("performance", "/api/v1/performance"),
            ("resilience", "/api/v1/resilience/certifications"),
            ("security", "/api/v1/security/assessments"),
        ):
            _, body = admin.request(path)
            page_summaries[name] = {
                "count": body.get(
                    "count",
                    len(body.get("items", []))
                    if isinstance(body, dict) and isinstance(body.get("items"), list)
                    else 0,
                ),
                "status": body.get("status"),
            }
    except (RuntimeError, TypeError, AttributeError, KeyError):
        page_summaries = {}
    report = {
        "application_commit": application_commit,
        "demo_id": state.demo_id,
        "scenario_registry_version": SCENARIO_REGISTRY_VERSION,
        "dataset": DATASET_NAME,
        "patient_count": 100,
        "dataset_id": state.dataset_id,
        "web_url": f"{WEB_BASE}/demo",
        "langgraph_run_id": state.langgraph_run_id,
        "crewai_run_id": state.crew_run_id,
        "candidate_metrics": {
            key: langgraph_metrics.get(key)
            for key in (
                "candidate_count",
                "included_count",
                "excluded_count",
                "evidence_resource_count",
                "evidence_count",
                "required_criterion_provenance_coverage",
                "reviewer_decision",
            )
        },
        "crewai_metrics": crew_metrics,
        "observability_metrics": observability,
        "page_summaries": page_summaries,
        "operations": state.operations,
        "screenshots": screenshots,
        "video_directory": str((output / "video").relative_to(ROOT))
        if (output / "video").exists()
        else None,
        "limitations": [
            "Synthetic development demonstration only.",
            "Not clinically validated or production certified.",
            "Security scanner results explicitly report unavailable scanners as not evaluable.",
        ],
    }
    json_path = output / "demo-report.json"
    md_path = output / "demo-report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(
        "# OncoAgent client demo\n\n"
        + "\n".join(
            f"- **{key}:** {value}"
            for key, value in report.items()
            if key
            not in {"operations", "limitations", "candidate_metrics", "screenshots"}
        )
        + "\n\n## Measured synthetic impact\n\n"
        + "\n".join(
            f"- **{key}:** {value}"
            for key, value in report["candidate_metrics"].items()
        )
        + "\n\n## Operations\n\n"
        + "\n".join(f"- {item['name']}: {item['status']}" for item in state.operations)
        + "\n\n## Screenshots\n\n"
        + "\n".join(f"- `{item}`" for item in screenshots)
        + "\n\n## Limitations\n\n"
        + "\n".join(f"- {item}" for item in report["limitations"])
        + "\n",
        encoding="utf-8",
    )
    return json_path


def latest_demo_id() -> str | None:
    states = sorted(
        OUTPUT_ROOT.glob("*/state.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return states[0].parent.name if states else None


def _check_item(checks: list[dict[str, str]], name: str, passed: bool) -> None:
    checks.append({"name": name, "status": "passed" if passed else "failed"})


def _worker_is_healthy() -> bool:
    try:
        output = subprocess.check_output(
            [
                DOCKER,
                "ps",
                "--filter",
                "label=com.docker.compose.project=oncoagent",
                "--filter",
                "label=com.docker.compose.service=temporal-worker",
                "--format",
                "{{.ID}}",
            ],
            text=True,
            timeout=10,
        )
        container_ids = [line for line in output.splitlines() if line.strip()]
        if len(container_ids) != 1:
            return False
        status = subprocess.check_output(
            [
                DOCKER,
                "inspect",
                "--format",
                "{{.State.Status}} {{.State.Health.Status}}",
                container_ids[0],
            ],
            text=True,
            timeout=10,
        ).strip()
        return status == "running healthy"
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def check() -> int:
    checks: list[dict[str, str]] = []
    values = dotenv_values(DEMO_ENV) if DEMO_ENV.exists() else {}
    client_id = str(values.get("CREWAI_MCP_CLIENT_ID") or "").strip()
    token = str(values.get("CREWAI_MCP_TOKEN") or "").strip()
    datasets = {
        item.strip()
        for item in str(values.get("CREWAI_MCP_DATASET_IDS") or "").split(",")
        if item.strip()
    }
    mcp_url = str(values.get("CREWAI_MCP_URL") or "").strip()
    api_base = str(values.get("DEMO_API_BASE") or API_BASE).rstrip("/")
    web_base = str(values.get("DEMO_WEB_BASE") or WEB_BASE).rstrip("/")

    _check_item(checks, "CrewAI MCP client ID configured", client_id == DEMO_CLIENT_ID)
    _check_item(checks, "CrewAI MCP token configured", bool(token))
    _check_item(
        checks,
        "CrewAI MCP URL valid",
        urlparse(mcp_url).scheme in {"http", "https"}
        and bool(urlparse(mcp_url).netloc),
    )
    _check_item(
        checks, "CrewAI dataset allowlist configured", datasets == {DEMO_DATASET_ID}
    )

    clients = {}
    try:
        clients = configured_clients(
            Settings(
                mcp_dev_clients=str(values.get("MCP_DEV_CLIENTS") or ""),
                crewai_enabled=False,
                temporal_enabled=False,
            )
        )
    except MCPAuthError:
        pass
    identity = clients.get(client_id)
    _check_item(checks, "MCP registry contains matching client", identity is not None)
    token_matches = bool(
        token
        and identity
        and hmac.compare_digest(
            hashlib.sha256(token.encode()).digest(),
            hashlib.sha256(identity.token.encode()).digest(),
        )
    )
    _check_item(checks, "MCP token fingerprint matches", token_matches)
    _check_item(
        checks,
        "MCP registry allows exact dataset",
        bool(identity and identity.dataset_ids == frozenset({DEMO_DATASET_ID})),
    )

    registry = build_tool_registry()
    tool_policy_ok = (
        set(registry) == REQUIRED_MCP_TOOLS
        and identity is not None
        and all(
            tool.descriptor.read_only
            and identity.actor_role in tool.descriptor.allowed_roles
            for tool in registry.values()
        )
    )
    _check_item(checks, "MCP required read-only tools allowed", tool_policy_ok)

    api_url = urlparse(api_base)
    web_url = urlparse(web_base)
    canonical_origins = (
        api_url.scheme == "http"
        and api_url.hostname == "127.0.0.1"
        and api_url.port == 8000
        and web_url.scheme == "http"
        and web_url.hostname == "127.0.0.1"
        and web_url.port == 3000
    )
    _check_item(checks, "Frontend and API use canonical host", canonical_origins)

    for name, url in (
        ("FastAPI ready", f"{api_base}/health"),
        ("Frontend ready", f"{web_base}/login"),
    ):
        try:
            with build_opener().open(Request(url), timeout=5) as response:
                ready = 200 <= response.status < 400
        except (OSError, HTTPError, URLError):
            ready = False
        _check_item(checks, name, ready)

    _check_item(checks, "Temporal worker healthy", _worker_is_healthy())

    browser_session_ok = False
    try:
        researcher = LocalApi("researcher-console", "researcher")
        login_status, _ = researcher.request(
            "/api/v1/auth/login", "POST", {"user_key": "researcher-console"}
        )
        me_status, me = researcher.request("/api/v1/auth/me")
        browser_session_ok = (
            login_status == 200
            and me_status == 200
            and isinstance(me, dict)
            and me.get("subject") == "researcher-console"
        )
    except (OSError, RuntimeError):
        pass
    _check_item(checks, "Login and auth/me round trip", browser_session_ok)

    print(json.dumps({"checks": checks}, indent=2))
    return 0 if all(item["status"] == "passed" for item in checks) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["check", "populate", "research", "operations", "report", "status"],
    )
    parser.add_argument("--demo-id")
    args = parser.parse_args()
    if args.command == "check":
        return check()
    if args.command == "status":
        print(
            json.dumps(
                {
                    "reports": [
                        str(path)
                        for path in sorted(OUTPUT_ROOT.glob("*/demo-report.json"))
                    ]
                },
                indent=2,
            )
        )
        return 0
    if args.command == "report":
        demo_id = args.demo_id or latest_demo_id()
        if not demo_id:
            print("no demo state exists", file=sys.stderr)
            return 1
        state = DemoRun.load_or_create(demo_id)
        print(write_report(state))
        return 0
    demo_id = args.demo_id or f"{now_id()}-{uuid4().hex[:6]}"
    state = DemoRun.load_or_create(demo_id)
    try:
        if args.command in {"populate", "research"}:
            populate_langgraph(state)
        if args.command in {"populate", "operations"}:
            populate_crewai(state)
        if args.command in {"populate", "operations"}:
            run_command(
                state,
                "performance_api_read_light",
                ["scripts/performance_runner.py", "--profile", "api-read-light"],
            )
            run_command(
                state,
                "security_assessment",
                ["scripts/security_scan.py", "--check", "all", "--persist"],
            )
        write_report(state)
        print(
            json.dumps(
                {"demo_id": state.demo_id, "operations": state.operations}, indent=2
            )
        )
        return 0
    except (RuntimeError, TimeoutError) as exc:
        state.operations.append(
            {"name": "orchestrator", "status": "failed", "reason": str(exc)}
        )
        write_report(state)
        print("demo population failed safely", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
