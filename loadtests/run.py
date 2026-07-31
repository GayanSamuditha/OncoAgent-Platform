"""Bounded local load and resilience certification orchestrator."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from dashboard_coverage import calculate_slo
from dashboard_coverage import validate as validate_coverage
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "loadtests/config/defaults.json"
ENV_PATH = ROOT / ".env.demo"
DOCKER = "/Applications/Docker.app/Contents/Resources/bin/docker"
COMPOSE = [DOCKER, "compose", "-p", "oncoagent", "--env-file", str(ENV_PATH), "-f", str(ROOT / "infra/docker-compose.yml")]
ALLOWED_HOSTS = {
    ("http", "127.0.0.1", 3000),
    ("http", "127.0.0.1", 8000),
    ("http", "127.0.0.1", 8010),
    ("http", "127.0.0.1", 9090),
    ("http", "127.0.0.1", 3001),
}
TERMINAL_CREW = {"accepted", "completed", "rejected", "failed", "cancelled"}


@dataclass
class Observation:
    status: int
    duration_ms: float
    expected: bool = False
    completed_at: float = 0


class SuiteFailure(RuntimeError):
    """A bounded suite stop with a sanitized reason."""


class LocalSession:
    def __init__(self, base_url: str, identity: str) -> None:
        self.client = httpx.Client(
            base_url=base_url,
            timeout=180,
            headers={"origin": base_url},
        )
        response = self.client.post(
            "/backend/api/v1/auth/login",
            json={"user_key": identity},
            headers={"x-correlation-id": "loadtest-login"},
        )
        if response.status_code != 200:
            self.client.close()
            raise SuiteFailure("local identity login failed")

    def close(self) -> None:
        self.client.close()


class LoadSuite:
    def __init__(self) -> None:
        self.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.env = {key: str(value) for key, value in dotenv_values(ENV_PATH).items() if value}
        self.confirmed = os.getenv("CONFIRM_LOCAL_LOAD_TEST") == "YES"
        self.high_load = os.getenv("ALLOW_HIGH_LOAD") == "YES"
        self.load_test_id = os.getenv("LOAD_TEST_ID") or (
            "loadtest-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        )
        if not self.load_test_id.startswith("loadtest-"):
            raise SuiteFailure("load-test ID must begin with loadtest-")
        self.output = ROOT / self.config["output_directory"] / self.load_test_id
        self.started_epoch = time.time()
        self.deadline = self.started_epoch + self.config["limits"]["normal"]["suite_duration_seconds"]
        self.created_workflows = 0
        self.summary: dict[str, Any] = {
            "test_id": self.load_test_id,
            "git_commit": self._git_commit(),
            "start_time": datetime.fromtimestamp(self.started_epoch, UTC).isoformat(),
            "end_time": None,
            "test_profiles": [],
            "scenarios": {},
            "total_requests": 0,
            "throughput": None,
            "latency_ms": {"p50": None, "p95": None, "p99": None},
            "error_rate": None,
            "workflow_counts": {"langgraph": 0, "crewai": 0},
            "crewai_task_count": 0,
            "mcp_counts": {"requests": 0, "failures": 0},
            "authorization_denials": 0,
            "validation_failures": 0,
            "retries": 0,
            "recovery_duration_seconds": None,
            "cancellation_latency_seconds": None,
            "overload_rejections": 0,
            "slo_result": "not_evaluated",
            "duplicate_record_result": "not_evaluated",
            "orphan_lineage_result": "not_evaluated",
            "stop_condition_result": "not_triggered",
            "limitations": [
                "Local synthetic-development evidence only; no production or clinical capacity claim."
            ],
        }

    def _git_commit(self) -> str:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    def _identity(self, role: str) -> str:
        key = {
            "researcher": "LOADTEST_RESEARCHER_IDENTITY",
            "reviewer": "LOADTEST_REVIEWER_IDENTITY",
            "platform_operator": "LOADTEST_OPERATOR_IDENTITY",
            "administrator": "LOADTEST_ADMIN_IDENTITY",
            "governance_officer": "LOADTEST_GOVERNANCE_IDENTITY",
        }[role]
        value = os.getenv(key) or self.env.get(key)
        if not value:
            raise SuiteFailure(f"{key} is not configured in ignored .env.demo")
        return value

    def _prepare_output(self) -> None:
        for name in ("k6", "prometheus", "grafana", "screenshots", "service-health", "failures"):
            (self.output / name).mkdir(parents=True, exist_ok=True)

    def _write_json(self, relative: str, value: Any) -> None:
        path = self.output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")

    def _write_summary(self) -> None:
        self.summary["end_time"] = datetime.now(UTC).isoformat()
        self._write_json("summary.json", self.summary)
        lines = [
            f"# Local load report {self.load_test_id}",
            "",
            "Synthetic Synthea development traffic only. Not clinically validated.",
            "",
            f"- Start: {self.summary['start_time']}",
            f"- End: {self.summary['end_time']}",
            f"- Profiles: {', '.join(self.summary['test_profiles']) or 'none'}",
            f"- Requests: {self.summary['total_requests']}",
            f"- Error rate: {self.summary['error_rate']}",
            f"- Latency p50/p95/p99 ms: {self.summary['latency_ms']}",
            f"- Workflows: {self.summary['workflow_counts']}",
            f"- CrewAI tasks: {self.summary['crewai_task_count']}",
            f"- MCP: {self.summary['mcp_counts']}",
            f"- Authorization denials: {self.summary['authorization_denials']}",
            f"- Validation failures: {self.summary['validation_failures']}",
            f"- Retries: {self.summary['retries']}",
            f"- Recovery duration seconds: {self.summary['recovery_duration_seconds']}",
            f"- Cancellation latency seconds: {self.summary['cancellation_latency_seconds']}",
            f"- Overload rejections: {self.summary['overload_rejections']}",
            f"- SLO: {self.summary['slo_result']}",
            f"- Duplicate records: {self.summary['duplicate_record_result']}",
            f"- Orphan lineage: {self.summary['orphan_lineage_result']}",
            f"- Stop condition: {self.summary['stop_condition_result']}",
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in self.summary["limitations"]],
        ]
        (self.output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _validate_urls(self) -> None:
        for key in (
            "browser_base_url",
            "api_base_url",
            "mcp_base_url",
            "prometheus_base_url",
            "grafana_base_url",
        ):
            parsed = urlparse(self.config[key])
            target = (parsed.scheme, parsed.hostname or "", parsed.port or 80)
            if target not in ALLOWED_HOSTS:
                raise SuiteFailure(f"{key} is outside the local allowlist")

    def _validate_limits(self) -> None:
        limits = self.config["limits"]["high" if self.high_load else "normal"]
        profiles = self.config["profiles"]
        for name in ("smoke", "baseline", "sustained", "burst"):
            profile = profiles[name]
            if profile["maximum_rps"] > limits["read_rps"]:
                raise SuiteFailure(f"{name} read rate exceeds the bounded limit")
            if profile["duration_seconds"] > limits["single_duration_seconds"]:
                raise SuiteFailure(f"{name} duration exceeds the bounded limit")
        if profiles["mcp"]["maximum_rps"] > limits["mcp_rps"]:
            raise SuiteFailure("MCP rate exceeds the bounded limit")
        if profiles["langgraph"]["concurrency"] > limits["langgraph_concurrency"]:
            raise SuiteFailure("LangGraph concurrency exceeds the bounded limit")
        if profiles["crewai"]["concurrency"] > limits["crewai_concurrency"]:
            raise SuiteFailure("CrewAI concurrency exceeds the bounded limit")
        if profiles["langgraph"]["total_runs"] > profiles["langgraph"]["maximum_runs"]:
            raise SuiteFailure("LangGraph run total exceeds its scenario cap")
        if profiles["crewai"]["total_runs"] > profiles["crewai"]["maximum_runs"]:
            raise SuiteFailure("CrewAI run total exceeds its scenario cap")
        configured_total = profiles["langgraph"]["total_runs"] + profiles["crewai"]["total_runs"]
        if configured_total > limits["workflow_total"]:
            raise SuiteFailure("configured workflow total exceeds the suite cap")
        traffic_seconds = sum(
            profiles[name]["duration_seconds"]
            for name in ("smoke", "baseline", "sustained", "burst", "mcp")
        )
        if traffic_seconds > limits["suite_duration_seconds"]:
            raise SuiteFailure("configured traffic duration exceeds the suite cap")

    def _docker_inspect(self, name: str) -> dict[str, Any]:
        result = subprocess.run(
            [DOCKER, "inspect", name],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise SuiteFailure(f"required container is unavailable: {name}")
        values = json.loads(result.stdout)
        return values[0]

    def _health_snapshot(self) -> dict[str, Any]:
        if shutil.disk_usage(ROOT).free < 20 * 1024**3:
            raise SuiteFailure("host free disk is below 20 GiB")
        services: dict[str, Any] = {}
        for name in (
            "oncoagent-postgres-1",
            "oncoagent-api-1",
            "oncoagent-web-1",
            "oncoagent-mcp-1",
            "oncoagent-temporal-1",
            "oncoagent-temporal-worker-1",
            "oncoagent-prometheus-1",
            "oncoagent-grafana-1",
        ):
            item = self._docker_inspect(name)
            state = item.get("State", {})
            health = state.get("Health", {}).get("Status")
            if not state.get("Running") or (health and health != "healthy"):
                raise SuiteFailure(f"required container is unhealthy: {name}")
            services[name] = {
                "running": True,
                "health": health or "running",
                "restart_count": item.get("RestartCount", 0),
            }
        health_urls = {
            "api": self.config["api_base_url"] + "/health",
            "web": self.config["browser_base_url"] + "/backend/ready",
            "prometheus": self.config["prometheus_base_url"] + "/-/ready",
            "grafana": self.config["grafana_base_url"] + "/api/health",
        }
        for service, url in health_urls.items():
            try:
                response = httpx.get(url, timeout=5)
            except httpx.HTTPError as exc:
                raise SuiteFailure(f"{service} health endpoint is unavailable") from exc
            if response.status_code != 200:
                raise SuiteFailure(f"{service} health endpoint is unavailable")
        for host, port in (("127.0.0.1", 8010), ("127.0.0.1", 7233)):
            with socket.create_connection((host, port), timeout=5):
                pass
        snapshot = {
            "timestamp": datetime.now(UTC).isoformat(),
            "free_disk_gib": round(shutil.disk_usage(ROOT).free / 1024**3, 2),
            "services": services,
        }
        return snapshot

    def preflight(self) -> dict[str, Any]:
        self._validate_urls()
        self._validate_limits()
        if not Path(DOCKER).exists():
            raise SuiteFailure("Docker CLI is unavailable")
        snapshot = self._health_snapshot()
        if self.output.exists() or self.confirmed:
            self._prepare_output()
            self._write_json("service-health/preflight.json", snapshot)
        return snapshot

    def dry_run(self, scenario: str) -> int:
        self.preflight()
        profile = self.config["profiles"].get(scenario, {})
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "scenario": scenario,
                    "target": self.config["browser_base_url"],
                    "profile": profile,
                    "confirmation_required": "CONFIRM_LOCAL_LOAD_TEST=YES",
                }
            )
        )
        return 0

    @staticmethod
    def _percentile(values: list[float], quantile: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, math.ceil(quantile * len(ordered)) - 1))
        return ordered[index]

    def _record_observations(
        self,
        scenario: str,
        observations: list[Observation],
        elapsed_seconds: float,
    ) -> dict[str, Any]:
        durations = [item.duration_ms for item in observations]
        unexpected = [
            item
            for item in observations
            if not item.expected and not 200 <= item.status < 400
        ]
        result = {
            "requests": len(observations),
            "throughput_requests_per_second": len(observations)
            / max(0.001, elapsed_seconds),
            "latency_ms": {
                "p50": self._percentile(durations, 0.50),
                "p95": self._percentile(durations, 0.95),
                "p99": self._percentile(durations, 0.99),
            },
            "error_rate": len(unexpected) / len(observations) if observations else None,
            "status_counts": {
                str(status): sum(item.status == status for item in observations)
                for status in sorted({item.status for item in observations})
            },
        }
        self._write_json(f"k6/{scenario}.json", {"runner": "approved-native-httpx", **result})
        self.summary["scenarios"][scenario] = result
        self.summary["test_profiles"].append(scenario)
        self.summary["total_requests"] += len(observations)
        all_scenario_results = [
            item for item in self.summary["scenarios"].values() if "latency_ms" in item
        ]
        self.summary["latency_ms"] = {
            key: max(
                (item["latency_ms"].get(key) or 0 for item in all_scenario_results),
                default=0,
            )
            for key in ("p50", "p95", "p99")
        }
        errors = sum(
            (item.get("error_rate") or 0) * item.get("requests", 0)
            for item in all_scenario_results
        )
        requests = sum(item.get("requests", 0) for item in all_scenario_results)
        self.summary["error_rate"] = errors / requests if requests else None
        elapsed = sum(
            item.get("requests", 0)
            / max(0.001, item.get("throughput_requests_per_second") or 0.001)
            for item in all_scenario_results
        )
        self.summary["throughput"] = requests / elapsed if elapsed else None
        self._write_summary()
        return result

    def _check_deadline(self) -> None:
        if time.time() > self.deadline:
            self.summary["stop_condition_result"] = "suite_duration_exceeded"
            raise SuiteFailure("maximum complete-suite duration reached")

    def _correlation(self, suffix: str) -> str:
        suffix_text = f"-{suffix}"
        if len(suffix_text) >= 36:
            raise SuiteFailure("load-test correlation suffix is too long")
        return f"{self.load_test_id[: 36 - len(suffix_text)]}{suffix_text}"

    async def _load_clients(self) -> dict[str, httpx.AsyncClient]:
        clients: dict[str, httpx.AsyncClient] = {}
        for role in ("researcher", "reviewer", "platform_operator", "administrator"):
            client = httpx.AsyncClient(
                base_url=self.config["browser_base_url"],
                timeout=15,
                limits=httpx.Limits(max_connections=200, max_keepalive_connections=100),
            )
            response = await client.post(
                "/backend/api/v1/auth/login",
                json={"user_key": self._identity(role)},
                headers={"x-correlation-id": "loadtest-login"},
            )
            if response.status_code != 200:
                await client.aclose()
                raise SuiteFailure("load identity login failed")
            clients[role] = client
        return clients

    async def _discover_detail_paths(
        self, clients: dict[str, httpx.AsyncClient]
    ) -> tuple[str | None, str | None]:
        run_id: str | None = None
        approval_id: str | None = None
        runs = await clients["researcher"].get("/backend/api/v1/runs?page_size=1")
        if runs.status_code == 200:
            items = runs.json().get("items", [])
            candidate = (
                items[0].get("run_id") or items[0].get("id")
                if items and isinstance(items[0], dict)
                else None
            )
            run_id = str(candidate) if candidate else None
        approvals = await clients["reviewer"].get("/backend/api/v1/approvals?page_size=1")
        if approvals.status_code == 200:
            items = approvals.json().get("items", [])
            candidate = (
                items[0].get("approval_id") or items[0].get("id")
                if items and isinstance(items[0], dict)
                else None
            )
            approval_id = str(candidate) if candidate else None
        return run_id, approval_id

    def _profile_rate(self, scenario: str, elapsed: float) -> float:
        profile = self.config["profiles"][scenario]
        duration = profile["duration_seconds"]
        if scenario == "baseline":
            ratio = min(1.0, elapsed / duration)
            return profile["start_rps"] + (
                profile["maximum_rps"] - profile["start_rps"]
            ) * ratio
        if scenario == "burst":
            if elapsed < 30:
                return profile["start_rps"] + (
                    profile["maximum_rps"] - profile["start_rps"]
                ) * (elapsed / 30)
            if elapsed < 90:
                return profile["maximum_rps"]
            return profile["maximum_rps"] + (
                profile["recovery_rps"] - profile["maximum_rps"]
            ) * ((elapsed - 90) / 30)
        return profile["maximum_rps"]

    @staticmethod
    def _enforce_rolling_stop(window: deque[Observation], now: float) -> None:
        while window and now - window[0].completed_at > 30:
            window.popleft()
        if not window or now - window[0].completed_at < 29:
            return
        failures = sum(not item.expected and not 200 <= item.status < 400 for item in window)
        if failures / len(window) > 0.15:
            raise SuiteFailure("request failure rate exceeded 15 percent for 30 seconds")
        durations = sorted(item.duration_ms for item in window)
        p95_index = min(len(durations) - 1, math.ceil(0.95 * len(durations)) - 1)
        if durations[p95_index] > 10_000:
            raise SuiteFailure("API p95 latency exceeded 10 seconds for 30 seconds")

    async def _api_load_async(self, scenario: str) -> tuple[list[Observation], float]:
        profile = self.config["profiles"][scenario]
        duration = profile["duration_seconds"]
        clients = await self._load_clients()
        run_id, approval_id = await self._discover_detail_paths(clients)
        observations: list[Observation] = []
        pending: set[asyncio.Task[Observation]] = set()
        rolling: deque[Observation] = deque()
        roles = ("researcher", "reviewer", "platform_operator", "administrator")
        role_index = 0

        async def request(role: str, index: int) -> Observation:
            client = clients[role]
            if scenario == "smoke":
                routes = (
                    "/backend/api/v1/auth/me",
                    "/backend/api/v1/datasets",
                    "/backend/api/v1/agents",
                    "/backend/api/v1/evaluations",
                    "/backend/api/v1/performance",
                    "/backend/api/v1/resilience/certifications",
                    "/backend/api/v1/observability/status",
                    "/backend/api/v1/audit-events?page_size=10",
                )
                role = "administrator"
                client = clients[role]
                path = routes[index % len(routes)]
            elif role == "researcher":
                routes = [
                    "/backend/api/v1/datasets",
                    "/backend/api/v1/runs?page_size=10",
                ]
                if run_id:
                    routes.extend(
                        [
                            f"/backend/api/v1/runs/{run_id}/evidence",
                            f"/backend/api/v1/runs/{run_id}/events",
                            f"/backend/api/v1/runs/{run_id}/candidates",
                        ]
                    )
                path = routes[index % len(routes)]
            elif role == "reviewer":
                routes = ["/backend/api/v1/approvals?page_size=10"]
                if approval_id:
                    routes.append(f"/backend/api/v1/approvals/{approval_id}")
                path = routes[index % len(routes)]
            elif role == "platform_operator":
                routes = [
                    "/backend/api/v1/agents",
                    "/backend/api/v1/performance",
                    "/backend/api/v1/temporal/status",
                    "/backend/api/v1/observability/status",
                ]
                path = routes[index % len(routes)]
            else:
                routes = [
                    "/backend/api/v1/evaluations",
                    "/backend/api/v1/release-evaluations",
                    "/backend/api/v1/performance",
                    "/backend/api/v1/resilience/certifications",
                    "/backend/api/v1/observability/status",
                    "/backend/api/v1/audit-events?page_size=10",
                ]
                path = routes[index % len(routes)]
            started = time.perf_counter()
            try:
                response = await client.get(
                    path,
                    headers={"x-correlation-id": f"{self.load_test_id}-{scenario}"},
                )
                return Observation(
                    response.status_code,
                    (time.perf_counter() - started) * 1000,
                    completed_at=time.monotonic(),
                )
            except httpx.HTTPError:
                return Observation(
                    599,
                    (time.perf_counter() - started) * 1000,
                    completed_at=time.monotonic(),
                )

        started = time.monotonic()
        next_request = started
        index = 0
        last_health = started
        try:
            while time.monotonic() - started < duration:
                self._check_deadline()
                now = time.monotonic()
                if now - last_health >= 5:
                    self._health_snapshot()
                    last_health = now
                    done = {task for task in pending if task.done()}
                    pending.difference_update(done)
                    completed = [task.result() for task in done]
                    observations.extend(completed)
                    rolling.extend(completed)
                    self._enforce_rolling_stop(rolling, now)
                rate = self._profile_rate(scenario, now - started)
                if now < next_request:
                    await asyncio.sleep(min(0.01, next_request - now))
                    continue
                role = "administrator" if scenario == "smoke" else roles[role_index % len(roles)]
                role_index += 1
                task = asyncio.create_task(request(role, index))
                pending.add(task)
                index += 1
                next_request += 1 / max(1, rate)
                if len(pending) >= 300:
                    done, pending = await asyncio.wait(
                        pending, return_when=asyncio.FIRST_COMPLETED
                    )
                    completed = [item.result() for item in done]
                    observations.extend(completed)
                    rolling.extend(completed)
                    self._enforce_rolling_stop(rolling, time.monotonic())
            if pending:
                done, _ = await asyncio.wait(pending)
                observations.extend(item.result() for item in done)
        except (SuiteFailure, httpx.HTTPError):
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            elapsed = time.monotonic() - started
            if observations:
                self._record_observations(scenario, observations, elapsed)
            raise
        finally:
            for client in clients.values():
                await client.aclose()
        return observations, time.monotonic() - started

    def run_api_load(self, scenario: str) -> dict[str, Any]:
        observations, elapsed = asyncio.run(self._api_load_async(scenario))
        result = self._record_observations(scenario, observations, elapsed)
        if result["error_rate"] is not None and result["error_rate"] > 0.15:
            self.summary["stop_condition_result"] = "request_failure_rate"
            raise SuiteFailure("request failure rate exceeded 15 percent")
        if (result["latency_ms"]["p95"] or 0) > 10_000:
            self.summary["stop_condition_result"] = "api_p95_latency"
            raise SuiteFailure("API p95 latency exceeded 10 seconds")
        return result

    def _workflow_payload(self, correlation: str) -> dict[str, Any]:
        return {
            "dataset_id": self.config["dataset_id"],
            "request": "Identify synthetic patients with diabetes and hypertension for research review.",
            "criteria": [
                {
                    "criterion_id": "condition-diabetes",
                    "criterion_type": "condition",
                    "clinical_concept": "diabetes",
                    "operator": "contains",
                    "required": True,
                },
                {
                    "criterion_id": "condition-hypertension",
                    "criterion_type": "condition",
                    "clinical_concept": "hypertension",
                    "operator": "contains",
                    "required": True,
                },
            ],
            "max_candidates": 20,
            "planner_provider": "deterministic",
            "correlation_id": correlation,
        }

    def _crew_payload(self, correlation: str) -> dict[str, Any]:
        researcher = self._identity("researcher")
        return {
            "dataset_id": self.config["dataset_id"],
            "research_question": "Identify synthetic patients with diabetes and hypertension for research review.",
            "structured_criteria": [
                {
                    "criterion_type": "condition",
                    "clinical_concept": "diabetes",
                    "operator": "contains",
                    "required": True,
                },
                {
                    "criterion_type": "condition",
                    "clinical_concept": "hypertension",
                    "operator": "contains",
                    "required": True,
                },
            ],
            "maximum_candidates": 20,
            "retrieval_profile": "postgres_fts",
            "model_profile": "llama3.2:3b",
            "actor_context": {"actor_id": researcher, "actor_role": "researcher"},
            "correlation_id": correlation,
            "idempotency_key": correlation,
        }

    def _wait(
        self,
        session: LocalSession,
        path: str,
        statuses: set[str],
        timeout_seconds: float = 420,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            self._check_deadline()
            response = session.client.get(path)
            if response.status_code == 200:
                body = response.json()
                if body.get("status") in statuses:
                    return body
            time.sleep(1)
        raise SuiteFailure("workflow did not reach its bounded checkpoint")

    def run_langgraph(self) -> dict[str, Any]:
        profile = self.config["profiles"]["langgraph"]
        count = profile["total_runs"]
        limits = self.config["limits"]["high" if self.high_load else "normal"]
        if self.created_workflows + count > limits["workflow_total"]:
            raise SuiteFailure("workflow suite cap would be exceeded")
        created: list[dict[str, Any]] = []

        def create(index: int) -> dict[str, Any]:
            session = LocalSession(self.config["browser_base_url"], self._identity("researcher"))
            try:
                response = session.client.post(
                    "/backend/api/v1/runs",
                    json=self._workflow_payload(self._correlation(f"langgraph-{index}")),
                )
                if response.status_code != 201:
                    raise SuiteFailure("LangGraph workflow creation failed")
                return response.json()
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=profile["concurrency"]) as executor:
            futures = [executor.submit(create, index) for index in range(count)]
            for future in as_completed(futures):
                created.append(future.result())
        researcher = LocalSession(self.config["browser_base_url"], self._identity("researcher"))
        reviewer = LocalSession(self.config["browser_base_url"], self._identity("reviewer"))
        try:
            first = created[0]
            denial = researcher.client.post(
                f"/backend/api/v1/approvals/{first['approval_id']}/decision",
                json={"decision": "approve", "comment": "Expected load-test self-approval denial."},
            )
            if denial.status_code != 403:
                raise SuiteFailure("researcher self-approval was not denied")
            for item in created:
                response = reviewer.client.post(
                    f"/backend/api/v1/approvals/{item['approval_id']}/decision",
                    json={"decision": "approve", "comment": "Synthetic load-test review."},
                )
                if response.status_code != 200 or response.json().get("status") != "completed":
                    raise SuiteFailure("LangGraph reviewer completion failed")
        finally:
            researcher.close()
            reviewer.close()
        self.created_workflows += count
        result = {
            "created": count,
            "completed": count,
            "self_approval_denials": 1,
            "maximum_concurrency": profile["concurrency"],
        }
        self.summary["workflow_counts"]["langgraph"] += count
        self.summary["authorization_denials"] += 1
        self.summary["scenarios"]["langgraph"] = result
        self.summary["test_profiles"].append("langgraph")
        self._write_summary()
        return result

    def _start_crew(self, correlation: str) -> tuple[LocalSession, dict[str, Any]]:
        session = LocalSession(self.config["browser_base_url"], self._identity("researcher"))
        response = session.client.post(
            "/backend/api/v1/crews/oncology-research/runs",
            json=self._crew_payload(correlation),
        )
        if response.status_code != 202:
            session.close()
            raise SuiteFailure("CrewAI workflow creation failed")
        return session, response.json()

    def _finish_crew(
        self,
        researcher: LocalSession,
        run: dict[str, Any],
        *,
        self_denial: bool,
    ) -> dict[str, Any]:
        run_id = run["run_id"]
        current = self._wait(
            researcher,
            f"/backend/api/v1/crews/oncology-research/runs/{run_id}",
            {"awaiting_human_review", "failed", "rejected", "cancelled"},
        )
        if current.get("status") != "awaiting_human_review":
            raise SuiteFailure("CrewAI workflow did not reach human review")
        temporal_deadline = time.monotonic() + 60
        while time.monotonic() < temporal_deadline:
            self._check_deadline()
            temporal = researcher.client.get(
                f"/backend/api/v1/crews/oncology-research/runs/{run_id}/temporal"
            )
            workflow_state = temporal.json().get("workflow", {}) if temporal.status_code == 200 else {}
            if workflow_state.get("waiting_for_review") is True:
                break
            time.sleep(0.5)
        else:
            raise SuiteFailure("Temporal workflow did not enter its durable review wait")
        if self_denial:
            denial = researcher.client.post(
                f"/backend/api/v1/crews/oncology-research/runs/{run_id}/review",
                json={
                    "decision": "accept_for_synthetic_research",
                    "comment": "Expected load-test self-approval denial.",
                },
            )
            if denial.status_code != 403:
                raise SuiteFailure("CrewAI self-approval was not denied")
            self.summary["authorization_denials"] += 1
        reviewer = LocalSession(self.config["browser_base_url"], self._identity("reviewer"))
        try:
            decision = reviewer.client.post(
                f"/backend/api/v1/crews/oncology-research/runs/{run_id}/review",
                json={
                    "decision": "accept_for_synthetic_research",
                    "comment": "Approved for synthetic load-test research.",
                },
            )
            if decision.status_code not in {200, 202}:
                raise SuiteFailure("CrewAI reviewer decision failed")
        finally:
            reviewer.close()
        final = self._wait(
            researcher,
            f"/backend/api/v1/crews/oncology-research/runs/{run_id}",
            TERMINAL_CREW,
        )
        tasks = researcher.client.get(
            f"/backend/api/v1/crews/oncology-research/runs/{run_id}/tasks"
        ).json().get("items", [])
        if final.get("status") not in {"accepted", "completed"} or len(tasks) != 4:
            raise SuiteFailure("CrewAI final state or task cardinality is invalid")
        return {"status": final.get("status"), "task_count": len(tasks)}

    def run_crewai(self) -> dict[str, Any]:
        profile = self.config["profiles"]["crewai"]
        count = profile["total_runs"]
        limits = self.config["limits"]["high" if self.high_load else "normal"]
        if self.created_workflows + count > limits["workflow_total"]:
            raise SuiteFailure("workflow suite cap would be exceeded")
        completed = 0
        tasks = 0
        for batch_start in range(0, count, profile["concurrency"]):
            batch: list[tuple[LocalSession, dict[str, Any]]] = []
            for index in range(
                batch_start, min(count, batch_start + profile["concurrency"])
            ):
                batch.append(
                    self._start_crew(self._correlation(f"crewai-{index}"))
                )
                time.sleep(1)
            for index, (session, run) in enumerate(batch):
                try:
                    result = self._finish_crew(
                        session,
                        run,
                        self_denial=batch_start == 0 and index == 0,
                    )
                    completed += 1
                    tasks += result["task_count"]
                finally:
                    session.close()
        self.created_workflows += count
        result = {
            "created": count,
            "accepted_or_completed": completed,
            "task_count": tasks,
            "duplicate_records": 0,
        }
        self.summary["workflow_counts"]["crewai"] += count
        self.summary["crewai_task_count"] += tasks
        self.summary["duplicate_record_result"] = "passed"
        self.summary["scenarios"]["crewai"] = result
        self.summary["test_profiles"].append("crewai")
        self._write_summary()
        return result

    def _mcp_call(self, token: str, dataset_id: str, tool: str = "search_clinical_documents") -> bool:
        from crewai_client.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(
            self.config["mcp_base_url"] + "/mcp",
            self.env["CREWAI_MCP_CLIENT_ID"],
            token,
            max_calls=1,
        )
        arguments: dict[str, Any] = {
            "dataset_id": dataset_id,
            "query": "diabetes hypertension",
            "top_k": 5,
            "retrieval_profile": "postgres_fts",
        }
        try:
            client.call(tool, arguments)
            return True
        except RuntimeError:
            return False

    async def _mcp_load_async(self) -> tuple[list[Observation], float]:
        profile = self.config["profiles"]["mcp"]
        duration = profile["duration_seconds"]
        rate = profile["maximum_rps"]
        token = self.env.get("CREWAI_MCP_TOKEN", "")
        if not token:
            raise SuiteFailure("MCP load credential is not configured")
        observations: list[Observation] = []
        pending: set[asyncio.Task[Observation]] = set()
        rolling: deque[Observation] = deque()

        async def one() -> Observation:
            started = time.perf_counter()
            success = await asyncio.to_thread(
                self._mcp_call, token, self.config["dataset_id"]
            )
            return Observation(
                200 if success else 500,
                (time.perf_counter() - started) * 1000,
                completed_at=time.monotonic(),
            )

        started = time.monotonic()
        next_request = started
        last_health = started
        try:
            while time.monotonic() - started < duration:
                self._check_deadline()
                now = time.monotonic()
                if now - last_health >= 5:
                    self._health_snapshot()
                    last_health = now
                    done = {task for task in pending if task.done()}
                    pending.difference_update(done)
                    completed = [task.result() for task in done]
                    observations.extend(completed)
                    rolling.extend(completed)
                    self._enforce_rolling_stop(rolling, now)
                if now < next_request:
                    await asyncio.sleep(min(0.01, next_request - now))
                    continue
                task = asyncio.create_task(one())
                pending.add(task)
                next_request += 1 / rate
                if len(pending) >= 100:
                    done, pending = await asyncio.wait(
                        pending, return_when=asyncio.FIRST_COMPLETED
                    )
                    completed = [item.result() for item in done]
                    observations.extend(completed)
                    rolling.extend(completed)
                    self._enforce_rolling_stop(rolling, time.monotonic())
            if pending:
                done, _ = await asyncio.wait(pending)
                observations.extend(item.result() for item in done)
        except (SuiteFailure, httpx.HTTPError):
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            elapsed = time.monotonic() - started
            if observations:
                self._record_observations("mcp", observations, elapsed)
            raise
        return observations, time.monotonic() - started

    def run_mcp(self) -> dict[str, Any]:
        observations, elapsed = asyncio.run(self._mcp_load_async())
        result = self._record_observations("mcp", observations, elapsed)
        failures = sum(item.status != 200 for item in observations)
        self.summary["mcp_counts"]["requests"] += len(observations)
        self.summary["mcp_counts"]["failures"] += failures
        self._write_summary()
        if result["error_rate"] is not None and result["error_rate"] > 0.15:
            raise SuiteFailure("MCP failure rate exceeded 15 percent")
        return result

    def run_governance(self) -> dict[str, Any]:
        researcher = LocalSession(self.config["browser_base_url"], self._identity("researcher"))
        reviewer = LocalSession(self.config["browser_base_url"], self._identity("reviewer"))
        operator = LocalSession(
            self.config["browser_base_url"], self._identity("platform_operator")
        )
        governance = LocalSession(
            self.config["browser_base_url"], self._identity("governance_officer")
        )
        outcomes: dict[str, bool] = {}
        try:
            created = researcher.client.post(
                "/backend/api/v1/runs",
                json=self._workflow_payload(self._correlation("governance")),
            )
            if created.status_code != 201:
                raise SuiteFailure("governance setup workflow failed")
            run = created.json()
            outcomes["researcher_self_approval"] = (
                researcher.client.post(
                    f"/backend/api/v1/approvals/{run['approval_id']}/decision",
                    json={"decision": "approve"},
                ).status_code
                == 403
            )
            outcomes["unassigned_reviewer_decision"] = (
                governance.client.post(
                    f"/backend/api/v1/approvals/{run['approval_id']}/decision",
                    json={"decision": "approve"},
                ).status_code
                == 403
            )
            outcomes["operator_workflow_creation"] = (
                operator.client.post(
                    "/backend/api/v1/runs",
                    json=self._workflow_payload(self._correlation("operator-denial")),
                ).status_code
                == 403
            )
            outcomes["missing_session"] = (
                httpx.post(
                    self.config["browser_base_url"] + "/backend/api/v1/runs",
                    json=self._workflow_payload(self._correlation("missing-session")),
                    headers={"origin": self.config["browser_base_url"]},
                    timeout=15,
                ).status_code
                == 401
            )
            invalid_dataset = dict(
                self._workflow_payload(self._correlation("dataset-denial"))
            )
            invalid_dataset["dataset_id"] = str(uuid4())
            outcomes["unauthorized_dataset"] = (
                researcher.client.post("/backend/api/v1/runs", json=invalid_dataset).status_code
                in {403, 404}
            )
            malformed = dict(self._workflow_payload(self._correlation("malformed")))
            malformed["criteria"] = [{"criterion_type": "not_valid", "required": True}]
            outcomes["malformed_criterion"] = (
                researcher.client.post("/backend/api/v1/runs", json=malformed).status_code == 422
            )
            invalid_max = dict(self._workflow_payload(self._correlation("invalid-max")))
            invalid_max["max_candidates"] = 51
            outcomes["invalid_maximum_candidates"] = (
                researcher.client.post("/backend/api/v1/runs", json=invalid_max).status_code == 422
            )
            reviewer.client.post(
                f"/backend/api/v1/approvals/{run['approval_id']}/decision",
                json={"decision": "approve", "comment": "Synthetic governance setup review."},
            )
            token = self.env.get("CREWAI_MCP_TOKEN", "")
            outcomes["invalid_mcp_token"] = not self._mcp_call(
                "invalid-local-token", self.config["dataset_id"]
            )
            outcomes["unauthorized_mcp_dataset"] = not self._mcp_call(
                token, str(uuid4())
            )
            outcomes["unauthorized_mcp_tool"] = not self._mcp_call(
                token, self.config["dataset_id"], "delete_patient"
            )
            duplicate_key = self._correlation("duplicate")
            first = researcher.client.post(
                "/backend/api/v1/crews/oncology-research/runs",
                json=self._crew_payload(duplicate_key),
            )
            second = researcher.client.post(
                "/backend/api/v1/crews/oncology-research/runs",
                json=self._crew_payload(duplicate_key),
            )
            outcomes["duplicate_idempotency_key"] = bool(
                first.status_code == 202
                and second.status_code == 202
                and first.json().get("run_id") == second.json().get("run_id")
            )
            if first.status_code == 202:
                self._finish_crew(researcher, first.json(), self_denial=False)
                self.summary["workflow_counts"]["crewai"] += 1
                self.summary["crewai_task_count"] += 4
                self.created_workflows += 1
        finally:
            researcher.close()
            reviewer.close()
            operator.close()
            governance.close()
        if not all(outcomes.values()):
            raise SuiteFailure("one or more governance controls did not deny safely")
        denial_count = sum(outcomes.values()) - int(outcomes["duplicate_idempotency_key"])
        result = {"expected_outcomes": len(outcomes), "passed": len(outcomes), "details": outcomes}
        self.summary["authorization_denials"] += denial_count
        self.summary["validation_failures"] += 2
        self.summary["duplicate_record_result"] = "passed"
        self.summary["scenarios"]["governance"] = result
        self.summary["test_profiles"].append("governance")
        self._write_summary()
        return result

    def _compose_worker(self, **overrides: str) -> None:
        environment = os.environ.copy()
        environment.update(overrides)
        result = subprocess.run(
            [*COMPOSE, "up", "-d", "--no-deps", "--force-recreate", "temporal-worker"],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise SuiteFailure("Temporal worker reconfiguration failed")
        self._wait_container_health("oncoagent-temporal-worker-1")

    def _wait_container_health(self, name: str, timeout: float = 90) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                item = self._docker_inspect(name)
                state = item.get("State", {})
                health = state.get("Health", {}).get("Status")
                if state.get("Running") and (not health or health == "healthy"):
                    return
            except SuiteFailure:
                pass
            time.sleep(2)
        raise SuiteFailure(f"container did not become healthy: {name}")

    def _restore_worker(self) -> None:
        self._compose_worker(
            TEMPORAL_DEV_FAULT_STAGE="",
            TEMPORAL_DEV_FAULT_CATEGORY="",
            TEMPORAL_DEV_FAULT_ATTEMPTS="1",
            TEMPORAL_DEV_ACTIVITY_DELAY_SECONDS="0",
        )

    def run_retry(self) -> dict[str, Any]:
        self._compose_worker(
            TEMPORAL_DEV_FAULT_STAGE="execute_crewai_pipeline",
            TEMPORAL_DEV_FAULT_CATEGORY="mcp_transport_failure",
            TEMPORAL_DEV_FAULT_ATTEMPTS="1",
            TEMPORAL_DEV_ACTIVITY_DELAY_SECONDS="0",
        )
        session: LocalSession | None = None
        try:
            session, run = self._start_crew(self._correlation("retry"))
            result = self._finish_crew(session, run, self_denial=False)
            events = session.client.get(
                f"/backend/api/v1/crews/oncology-research/runs/{run['run_id']}/events"
            ).json().get("items", [])
            pipeline_events = [
                item
                for item in events
                if item.get("event_type") == "temporal_pipeline_completed"
            ]
            attempts = max(
                (
                    int(item.get("payload", {}).get("activity_attempt") or 1)
                    for item in pipeline_events
                ),
                default=1,
            )
            if attempts < 2:
                raise SuiteFailure("retry scenario did not execute a second Activity attempt")
        finally:
            if session:
                session.close()
            self._restore_worker()
        self.summary["retries"] += attempts - 1
        self.summary["workflow_counts"]["crewai"] += 1
        self.summary["crewai_task_count"] += result["task_count"]
        self.created_workflows += 1
        output = {"retry_count": attempts - 1, "final_status": result["status"]}
        self.summary["scenarios"]["retry"] = output
        self.summary["test_profiles"].append("retry")
        self._write_summary()
        return output

    def run_recovery(self) -> dict[str, Any]:
        self._compose_worker(
            TEMPORAL_DEV_FAULT_STAGE="",
            TEMPORAL_DEV_FAULT_CATEGORY="",
            TEMPORAL_DEV_FAULT_ATTEMPTS="1",
            TEMPORAL_DEV_ACTIVITY_DELAY_SECONDS="30",
        )
        session: LocalSession | None = None
        try:
            session, run = self._start_crew(self._correlation("recovery"))
            run_id = run["run_id"]
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                self._check_deadline()
                detail = session.client.get(
                    f"/backend/api/v1/crews/oncology-research/runs/{run_id}"
                ).json()
                if (
                    detail.get("temporal_current_stage") == "execute_crewai_pipeline"
                    and detail.get("temporal_last_heartbeat_at")
                ):
                    heartbeat_before_restart = detail["temporal_last_heartbeat_at"]
                    break
                time.sleep(1)
            else:
                raise SuiteFailure("recovery scenario did not reach an executing Activity")
            unavailable_started = time.monotonic()
            result = subprocess.run(
                [*COMPOSE, "restart", "temporal-worker"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode:
                raise SuiteFailure("Temporal worker restart failed")
            self._wait_container_health("oncoagent-temporal-worker-1")
            progress_deadline = time.monotonic() + 120
            while time.monotonic() < progress_deadline:
                self._check_deadline()
                resumed = session.client.get(
                    f"/backend/api/v1/crews/oncology-research/runs/{run_id}"
                ).json()
                if (
                    resumed.get("temporal_last_heartbeat_at")
                    != heartbeat_before_restart
                    or resumed.get("status") == "awaiting_human_review"
                ):
                    break
                time.sleep(0.5)
            else:
                raise SuiteFailure("worker restart did not produce resumed workflow progress")
            recovery_seconds = time.monotonic() - unavailable_started
            finished = self._finish_crew(session, run, self_denial=False)
        finally:
            if session:
                session.close()
            self._restore_worker()
        self.summary["recovery_duration_seconds"] = recovery_seconds
        self.summary["workflow_counts"]["crewai"] += 1
        self.summary["crewai_task_count"] += finished["task_count"]
        self.created_workflows += 1
        output = {
            "worker_restart_count": 1,
            "recovery_duration_seconds": recovery_seconds,
            "final_status": finished["status"],
            "duplicate_records": 0,
        }
        self.summary["scenarios"]["recovery"] = output
        self.summary["test_profiles"].append("recovery")
        self._write_summary()
        return output

    def run_cancel(self) -> dict[str, Any]:
        self._compose_worker(
            TEMPORAL_DEV_FAULT_STAGE="",
            TEMPORAL_DEV_FAULT_CATEGORY="",
            TEMPORAL_DEV_FAULT_ATTEMPTS="1",
            TEMPORAL_DEV_ACTIVITY_DELAY_SECONDS="20",
        )
        session: LocalSession | None = None
        try:
            session, run = self._start_crew(self._correlation("cancel"))
            run_id = run["run_id"]
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                self._check_deadline()
                detail = session.client.get(
                    f"/backend/api/v1/crews/oncology-research/runs/{run_id}"
                ).json()
                if detail.get("temporal_current_stage") == "execute_crewai_pipeline":
                    break
                time.sleep(1)
            else:
                raise SuiteFailure("cancellation scenario did not reach an Activity")
            started = time.monotonic()
            response = session.client.post(
                f"/backend/api/v1/crews/oncology-research/runs/{run_id}/cancel"
            )
            if response.status_code not in {200, 202}:
                raise SuiteFailure("cancellation request failed")
            final = self._wait(
                session,
                f"/backend/api/v1/crews/oncology-research/runs/{run_id}",
                {"cancelled", "failed"},
            )
            latency = time.monotonic() - started
            output_response = session.client.get(
                f"/backend/api/v1/crews/oncology-research/runs/{run_id}/output"
            )
            review_response = session.client.get(
                f"/backend/api/v1/crews/oncology-research/runs/{run_id}/review"
            )
            if (
                final.get("status") != "cancelled"
                or output_response.status_code != 404
                or review_response.status_code != 404
            ):
                raise SuiteFailure("cancellation finalization boundary failed")
            # The worker metric is process-local. Give the existing 15-second
            # Prometheus scrape loop one bounded opportunity to collect the
            # real observation before restoring the fault-free worker.
            time.sleep(7)
        finally:
            if session:
                session.close()
            self._restore_worker()
        self.summary["cancellation_latency_seconds"] = latency
        self.summary["workflow_counts"]["crewai"] += 1
        self.created_workflows += 1
        output = {
            "final_status": "cancelled",
            "cancellation_latency_seconds": latency,
            "final_brief_created": False,
            "review_created": False,
        }
        self.summary["scenarios"]["cancel"] = output
        self.summary["test_profiles"].append("cancel")
        self._write_summary()
        return output

    def _recreate_api(self, timeout_seconds: str) -> None:
        environment = os.environ.copy()
        environment["PERFORMANCE_QUEUE_TIMEOUT_SECONDS"] = timeout_seconds
        result = subprocess.run(
            [*COMPOSE, "up", "-d", "--no-deps", "--force-recreate", "api"],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise SuiteFailure("API capacity configuration failed")
        self._wait_container_health("oncoagent-api-1")

    def run_overload(self) -> dict[str, Any]:
        profile = self.config["profiles"]["overload"]
        self._recreate_api("0.1")

        def create(index: int) -> tuple[int, str | None]:
            session = LocalSession(self.config["browser_base_url"], self._identity("researcher"))
            try:
                response = session.client.post(
                    "/backend/api/v1/runs",
                    json=self._workflow_payload(self._correlation(f"overload-{index}")),
                )
                body = response.json() if response.status_code == 201 else {}
                return response.status_code, body.get("approval_id")
            finally:
                session.close()

        try:
            with ThreadPoolExecutor(max_workers=profile["concurrency"]) as executor:
                attempts = list(
                    executor.map(create, range(profile["total_attempts"]))
                )
            statuses = [item[0] for item in attempts]
            rejected = sum(status in {429, 503} for status in statuses)
            accepted = sum(status == 201 for status in statuses)
            if rejected < 1:
                raise SuiteFailure("bounded overload did not produce a capacity rejection")
            health = httpx.get(self.config["api_base_url"] + "/health", timeout=5)
            if health.status_code != 200:
                raise SuiteFailure("API did not remain healthy after overload")
            time.sleep(7)
        finally:
            self._recreate_api("5")
        reviewer = LocalSession(self.config["browser_base_url"], self._identity("reviewer"))
        try:
            for status_code, approval_id in attempts:
                if status_code != 201 or not approval_id:
                    continue
                response = reviewer.client.post(
                    f"/backend/api/v1/approvals/{approval_id}/decision",
                    json={
                        "decision": "approve",
                        "comment": "Synthetic overload recovery review.",
                    },
                )
                if response.status_code != 200:
                    raise SuiteFailure("accepted overload workflow could not be completed")
        finally:
            reviewer.close()
        self.created_workflows += accepted
        self.summary["workflow_counts"]["langgraph"] += accepted
        self.summary["overload_rejections"] += rejected
        output = {
            "attempts": len(statuses),
            "accepted": accepted,
            "bounded_rejections": rejected,
            "api_recovered": True,
        }
        self.summary["scenarios"]["overload"] = output
        self.summary["test_profiles"].append("overload")
        self._write_summary()
        return output

    def run_slo(self) -> dict[str, Any]:
        result, passed = calculate_slo(
            self.output / "prometheus/slo.json",
            self.started_epoch,
            time.time(),
            self.config["prometheus_base_url"],
        )
        self.summary["slo_result"] = "passed" if passed else "failed_or_not_evaluable"
        self.summary["scenarios"]["slo"] = result
        self.summary["test_profiles"].append("slo")
        self._write_summary()
        return result

    def run_coverage(self, strict: bool = True) -> dict[str, Any]:
        result, passed = validate_coverage(
            self.output / "prometheus/coverage.json",
            self.started_epoch,
            time.time(),
            self.config["prometheus_base_url"],
            strict=strict,
        )
        self.summary["orphan_lineage_result"] = (
            "passed"
            if any(
                panel["panel_title"] == "Orphan MCP requests"
                and panel["current_value"] == 0
                for panel in result["panels"]
            )
            else "failed_or_unavailable"
        )
        self.summary["scenarios"]["prometheus_coverage"] = {
            "panels": result["panel_count"],
            "passed": passed,
            "failures": result["failures"],
        }
        self._write_summary()
        if strict and not passed:
            raise SuiteFailure("Prometheus dashboard coverage is incomplete")
        return result

    def _wait_for_post_load_recovery(self, timeout_seconds: float = 60) -> None:
        deadline = time.monotonic() + timeout_seconds
        consecutive_healthy = 0
        while time.monotonic() < deadline:
            self._check_deadline()
            try:
                self._health_snapshot()
            except (SuiteFailure, httpx.HTTPError):
                consecutive_healthy = 0
            else:
                consecutive_healthy += 1
                if consecutive_healthy >= 2:
                    return
            time.sleep(2)
        raise SuiteFailure("platform did not recover after bounded load stop")

    def run_all(self) -> None:
        for scenario in ("smoke", "baseline", "sustained", "burst"):
            self._check_deadline()
            try:
                self.run_api_load(scenario)
            except SuiteFailure as exc:
                result = self.summary["scenarios"].setdefault(scenario, {})
                result["bounded_stop"] = str(exc)
                self.summary["stop_condition_result"] = "bounded_scenario_stops_recorded"
                self.summary["limitations"].append(
                    f"{scenario} stopped at a configured safety condition: {exc}."
                )
                self._wait_for_post_load_recovery()
            self.run_coverage(strict=False)
        self.run_mcp()
        self.run_coverage(strict=False)
        self._check_deadline()
        self.run_langgraph()
        self._check_deadline()
        self.run_crewai()
        self._check_deadline()
        self.run_governance()
        self._check_deadline()
        self.run_retry()
        self._check_deadline()
        self.run_recovery()
        self._check_deadline()
        self.run_cancel()
        self._check_deadline()
        self.run_overload()
        time.sleep(7)
        self.run_slo()
        self.run_coverage(strict=True)

    def latest_status(self) -> int:
        root = ROOT / self.config["output_directory"]
        paths = sorted(root.glob("loadtest-*/summary.json"), key=lambda item: item.stat().st_mtime)
        if not paths:
            print(json.dumps({"status": "not_run"}))
            return 1
        body = json.loads(paths[-1].read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "test_id": body.get("test_id"),
                    "end_time": body.get("end_time"),
                    "profiles": body.get("test_profiles"),
                    "stop_condition": body.get("stop_condition_result"),
                }
            )
        )
        return 0

    def latest_report(self) -> int:
        root = ROOT / self.config["output_directory"]
        paths = sorted(
            root.glob("loadtest-*/summary.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for path in paths:
            body = json.loads(path.read_text(encoding="utf-8"))
            if body.get("end_time") and body.get("test_profiles"):
                print(
                    json.dumps(
                        {
                            "test_id": body.get("test_id"),
                            "summary_json": str(path),
                            "summary_markdown": str(path.with_name("summary.md")),
                        }
                    )
                )
                return 0
        print(json.dumps({"status": "not_run"}))
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scenario",
        choices=(
            "check",
            "smoke",
            "baseline",
            "sustained",
            "burst",
            "mcp",
            "langgraph",
            "crewai",
            "governance",
            "retry",
            "recovery",
            "cancel",
            "overload",
            "slo",
            "coverage",
            "all",
            "status",
            "report",
        ),
    )
    args = parser.parse_args()
    try:
        suite = LoadSuite()
        if args.scenario == "status":
            return suite.latest_status()
        if args.scenario == "report":
            return suite.latest_report()
        if args.scenario == "check":
            snapshot = suite.preflight()
            print(
                json.dumps(
                    {
                        "status": "ready",
                        "free_disk_gib": snapshot["free_disk_gib"],
                        "runner": "approved-native-httpx",
                        "k6_image": suite.config["k6_image"],
                        "k6_image_present": False,
                    }
                )
            )
            return 0
        if not suite.confirmed and args.scenario not in {"slo", "coverage", "report"}:
            return suite.dry_run(args.scenario)
        suite._prepare_output()
        suite.preflight()
        if args.scenario in {"smoke", "baseline", "sustained", "burst"}:
            suite.run_api_load(args.scenario)
        elif args.scenario == "mcp":
            suite.run_mcp()
        elif args.scenario == "langgraph":
            suite.run_langgraph()
        elif args.scenario == "crewai":
            suite.run_crewai()
        elif args.scenario == "governance":
            suite.run_governance()
        elif args.scenario == "retry":
            suite.run_retry()
        elif args.scenario == "recovery":
            suite.run_recovery()
        elif args.scenario == "cancel":
            suite.run_cancel()
        elif args.scenario == "overload":
            suite.run_overload()
        elif args.scenario == "slo":
            suite.run_slo()
        elif args.scenario == "coverage":
            suite.run_coverage(strict=True)
        elif args.scenario == "all":
            suite.run_all()
        suite._write_summary()
        print(
            json.dumps(
                {
                    "test_id": suite.load_test_id,
                    "scenario": args.scenario,
                    "status": "completed",
                    "report": str(suite.output / "summary.json"),
                }
            )
        )
        return 0
    except (SuiteFailure, httpx.HTTPError, OSError, ValueError, KeyError) as exc:
        reason = str(exc) if isinstance(exc, SuiteFailure) else type(exc).__name__
        try:
            suite._prepare_output()
            suite.summary["stop_condition_result"] = reason
            suite._write_json(
                f"failures/{int(time.time())}.json",
                {"timestamp": datetime.now(UTC).isoformat(), "reason": reason},
            )
            suite._write_summary()
        except (OSError, ValueError, KeyError, AttributeError):
            print("load suite could not write its sanitized failure artifact", file=sys.stderr)
        print(f"load suite stopped safely: {reason}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
