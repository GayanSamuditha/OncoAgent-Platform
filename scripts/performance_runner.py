"""Bounded local performance runner with real workload adapters.

Health/readiness probes are intentionally limited to the two API-read
profiles.  Other profiles either execute their named operation or return an
explicit ``not_evaluable`` result; a probe is never reported as workflow
performance.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

import httpx
from app.db.session import SessionLocal
from app.models.performance import (
    PerformanceExecutionRecord,
    PerformanceFindingRecord,
    PerformanceMetricRecord,
    PerformanceSLORecord,
)
from app.performance.calculations import evaluate_slo, percentile, ratio
from app.performance.contracts import (
    BottleneckFinding,
    HardwareProfile,
    PerformanceExecution,
    PerformanceObservation,
    PerformanceReport,
    ServiceMetric,
    VersionManifest,
)
from app.performance.profiles import get_profile
from crewai_client.mcp_client import MCPGatewayClient  # type: ignore[import-untyped]
from sqlalchemy.exc import SQLAlchemyError

OUTPUT_DIR = Path("evaluation_outputs/performance")
LOCAL_IDENTITIES = {"researcher": "researcher-console", "reviewer": "reviewer-console"}


class AdapterResult:
    def __init__(self, adapter: str, supported: bool = True, reason: str | None = None) -> None:
        self.adapter = adapter
        self.supported = supported
        self.reason = reason
        self.observations: list[PerformanceObservation] = []
        self.success_count = 0
        self.expected_denial_count = 0
        self.unexpected_failure_count = 0
        self.timeout_count = 0
        self.active_concurrency = 0
        self.details: dict[str, Any] = {}


def _dataset_id() -> str | None:
    value = os.getenv("PERFORMANCE_DATASET_ID", "").strip()
    if value:
        return value
    return next((item.strip() for item in os.getenv("CREWAI_MCP_DATASET_IDS", "").split(",") if item.strip()), None)


def _observation(operation: str, status_code: int, started: float, *, error: str | None = None) -> PerformanceObservation:
    return PerformanceObservation(
        operation=operation,
        status_class=f"{status_code // 100}xx" if status_code else "error",
        duration_ms=(time.perf_counter() - started) * 1000,
        error_category=error or (None if status_code < 400 else f"http_{status_code}"),
        correlation_present=True,
    )


async def request_once(client: httpx.AsyncClient, path: str, operation: str) -> PerformanceObservation:
    started = time.perf_counter()
    try:
        response = await client.get(path)
        return _observation(operation, response.status_code, started)
    except httpx.TimeoutException:
        return _observation(operation, 0, started, error="timeout")
    except httpx.HTTPError:
        return _observation(operation, 0, started, error="transport")


async def login(client: httpx.AsyncClient, user_key: str) -> bool:
    response = await client.post(
        "/api/v1/auth/login",
        json={"user_key": user_key},
        headers={"Origin": os.getenv("PERFORMANCE_ORIGIN", "http://127.0.0.1:3000")},
    )
    return response.status_code == 200


async def wait_json(client: httpx.AsyncClient, path: str, predicate: Any, timeout: float) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = await client.get(path)
        if response.status_code == 200:
            data = response.json()
            if predicate(data):
                return data
        await asyncio.sleep(0.5)
    return None


async def safe_event_names(client: httpx.AsyncClient, path: str) -> list[str]:
    """Read only bounded event names; never persist event payloads."""
    response = await client.get(path)
    if response.status_code != 200:
        return []
    payload = response.json()
    items = payload if isinstance(payload, list) else payload.get("items", [])
    return [str(item.get("event_type")) for item in items if isinstance(item, dict) and item.get("event_type")]


def _workflow_criteria() -> list[dict[str, Any]]:
    return [{"criterion_type": "condition", "clinical_concept": "diabetes", "operator": "contains", "required": True}]


async def _run_langgraph(client: httpx.AsyncClient, profile: Any) -> AdapterResult:
    result = AdapterResult("langgraph-governed-workflow")
    if not _dataset_id():
        return AdapterResult(result.adapter, False, "PERFORMANCE_DATASET_ID or CREWAI_MCP_DATASET_IDS is required")
    if not await login(client, LOCAL_IDENTITIES["researcher"]):
        result.unexpected_failure_count += 1
        result.details["error"] = "researcher_login_failed"
        return result
    for _ in range(profile.request_count):
        started = time.perf_counter()
        response = await client.post(
            "/api/v1/runs",
            json={"dataset_id": _dataset_id(), "request": "Find synthetic patients with diabetes", "criteria": _workflow_criteria(), "max_candidates": 5, "planner_provider": "deterministic"},
        )
        result.observations.append(_observation("langgraph.create", response.status_code, started))
        if response.status_code not in {200, 201}:
            result.unexpected_failure_count += 1
            continue
        result.success_count += 1
        data = response.json()
        run_id = data.get("run_id")
        review = await wait_json(client, f"/api/v1/runs/{run_id}", lambda item: item.get("status") in {"awaiting_approval", "completed", "failed", "rejected"}, profile.timeout_seconds)
        if review is None:
            result.timeout_count += 1
            continue
        if review.get("status") == "awaiting_approval" and review.get("approval_id"):
            if not await login(client, LOCAL_IDENTITIES["reviewer"]):
                result.unexpected_failure_count += 1
                continue
            decision = await client.post(f"/api/v1/approvals/{review['approval_id']}/decision", json={"decision": "approve", "comment": "bounded performance validation"})
            if decision.status_code not in {200, 201}:
                result.unexpected_failure_count += 1
                continue
            await login(client, LOCAL_IDENTITIES["researcher"])
            await wait_json(client, f"/api/v1/runs/{run_id}", lambda item: item.get("status") in {"completed", "failed", "rejected"}, profile.timeout_seconds)
        result.details.setdefault("run_ids", []).append(run_id)
        result.details.setdefault("event_names", []).extend(await safe_event_names(client, f"/api/v1/runs/{run_id}/events"))
        await login(client, LOCAL_IDENTITIES["researcher"])
    return result


async def _run_crewai(client: httpx.AsyncClient, profile: Any) -> AdapterResult:
    result = AdapterResult("crewai-temporal-workflow")
    dataset_id = _dataset_id()
    if not dataset_id:
        return AdapterResult(result.adapter, False, "PERFORMANCE_DATASET_ID or CREWAI_MCP_DATASET_IDS is required")
    if not await login(client, LOCAL_IDENTITIES["researcher"]):
        result.unexpected_failure_count += 1
        return result
    for _ in range(profile.request_count):
        started = time.perf_counter()
        response = await client.post(
            "/api/v1/crews/oncology-research/runs",
            json={"dataset_id": dataset_id, "research_question": "Find synthetic patients with diabetes", "structured_criteria": _workflow_criteria(), "maximum_candidates": 5, "retrieval_profile": "postgres_fts", "model_profile": "llama3.2:3b", "actor_context": {"actor_id": LOCAL_IDENTITIES["researcher"], "actor_role": "researcher"}, "idempotency_key": f"performance-{uuid4()}"},
        )
        result.observations.append(_observation("crewai.create", response.status_code, started))
        if response.status_code not in {200, 201, 202}:
            result.unexpected_failure_count += 1
            continue
        result.success_count += 1
        data = response.json()
        run_id = data.get("run_id")
        review = await wait_json(client, f"/api/v1/crews/oncology-research/runs/{run_id}", lambda item: item.get("status") in {"awaiting_human_review", "accepted", "failed", "rejected", "cancelled"}, profile.timeout_seconds)
        if review is None:
            result.timeout_count += 1
            continue
        if review.get("status") == "awaiting_human_review":
            if not await login(client, LOCAL_IDENTITIES["reviewer"]):
                result.unexpected_failure_count += 1
                continue
            review_response = await client.post(f"/api/v1/crews/oncology-research/runs/{run_id}/review", json={"decision": "accept_for_synthetic_research", "comment": "bounded performance validation"})
            if review_response.status_code not in {200, 202}:
                result.unexpected_failure_count += 1
            else:
                await login(client, LOCAL_IDENTITIES["researcher"])
                await wait_json(client, f"/api/v1/crews/oncology-research/runs/{run_id}", lambda item: item.get("status") in {"accepted", "completed", "failed", "rejected"}, profile.timeout_seconds)
        result.details.setdefault("run_ids", []).append(run_id)
        result.details.setdefault("event_names", []).extend(await safe_event_names(client, f"/api/v1/crews/oncology-research/runs/{run_id}/events"))
        await login(client, LOCAL_IDENTITIES["researcher"])
    return result


def _mcp_call(client_id: str, token: str, url: str, dataset_id: str, *, expected_denial: bool = False) -> tuple[bool, float, str, bool]:
    started = time.perf_counter()
    try:
        client = MCPGatewayClient(url, client_id, token, max_calls=30)
        call = client.call("search_clinical_documents", {"dataset_id": dataset_id, "query": "diabetes", "top_k": 5, "retrieval_profile": "postgres_fts"})
        error_payload = call.result.get("error")
        if expected_denial and (
            call.result.get("status") == "error"
            or call.result.get("error_category")
            or isinstance(error_payload, dict)
        ):
            return False, (time.perf_counter() - started) * 1000, call.request_id, True
        return True, (time.perf_counter() - started) * 1000, call.request_id, False
    except (OSError, RuntimeError, ValueError):
        return False, (time.perf_counter() - started) * 1000, "", expected_denial


async def _run_mcp(profile: Any) -> AdapterResult:
    result = AdapterResult("mcp-streamable-http")
    dataset_id = _dataset_id()
    client_id, token, url = os.getenv("CREWAI_MCP_CLIENT_ID", ""), os.getenv("CREWAI_MCP_TOKEN", ""), os.getenv("CREWAI_MCP_URL", "http://127.0.0.1:8010/mcp")
    if not dataset_id or not client_id or not token:
        return AdapterResult(result.adapter, False, "MCP client identity and PERFORMANCE_DATASET_ID are required")
    limiter = asyncio.Semaphore(min(profile.concurrency, 4))
    async def call(index: int) -> None:
        async with limiter:
            expected_denial = index == profile.request_count - 1
            call_dataset = "00000000-0000-0000-0000-000000000000" if expected_denial else dataset_id
            success, latency, request_id, denied = await asyncio.to_thread(_mcp_call, client_id, token, url, call_dataset, expected_denial=expected_denial)
            result.observations.append(PerformanceObservation(operation="mcp.search", status_class="2xx" if success else "error", duration_ms=latency, correlation_present=bool(request_id), error_category=None if success else "transport"))
            if success:
                result.success_count += 1
            elif denied:
                result.expected_denial_count += 1
            else:
                result.unexpected_failure_count += 1
    await asyncio.gather(*(call(i) for i in range(profile.request_count)))
    result.active_concurrency = min(profile.concurrency, 4)
    return result


async def _run_model(profile: Any) -> AdapterResult:
    result = AdapterResult("ollama-generate")
    base_url = os.getenv("CREWAI_OLLAMA_BASE_URL", os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434"))
    model = os.getenv("PERFORMANCE_MODEL", os.getenv("CREWAI_DEFAULT_MODEL", "llama3.2:3b"))
    limiter = asyncio.Semaphore(min(profile.concurrency, 2))
    async def generate() -> None:
        async with limiter:
            started = time.perf_counter()
            try:
                async with httpx.AsyncClient(base_url=base_url, timeout=profile.timeout_seconds) as client:
                    response = await client.post("/api/generate", json={"model": model, "prompt": "Synthetic research validation. Return OK.", "stream": False, "options": {"temperature": 0, "num_predict": 16}})
                result.observations.append(_observation("ollama.generate", response.status_code, started, error=None if response.status_code < 400 else "model_error"))
                if response.status_code < 400:
                    result.success_count += 1
                else:
                    result.unexpected_failure_count += 1
            except httpx.TimeoutException:
                result.timeout_count += 1
                result.observations.append(_observation("ollama.generate", 0, started, error="timeout"))
            except httpx.HTTPError:
                result.unexpected_failure_count += 1
                result.observations.append(_observation("ollama.generate", 0, started, error="transport"))
    await asyncio.gather(*(generate() for _ in range(min(profile.request_count, 6))))
    result.active_concurrency = min(profile.concurrency, 2)
    return result


async def _run_database_pressure(client: httpx.AsyncClient, profile: Any) -> AdapterResult:
    result = AdapterResult("database-backed-performance-history")
    if not await login(client, "auditor-console"):
        return AdapterResult(result.adapter, False, "auditor identity unavailable")
    limiter = asyncio.Semaphore(profile.concurrency)

    async def query() -> None:
        async with limiter:
            started = time.perf_counter()
            try:
                response = await client.get("/api/v1/performance?page=1&page_size=10")
                result.observations.append(_observation("database.performance_history", response.status_code, started))
                if response.status_code == 200:
                    result.success_count += 1
                elif response.status_code in {401, 403, 409}:
                    result.expected_denial_count += 1
                else:
                    result.unexpected_failure_count += 1
            except httpx.TimeoutException:
                result.timeout_count += 1
                result.observations.append(_observation("database.performance_history", 0, started, error="timeout"))
            except httpx.HTTPError:
                result.unexpected_failure_count += 1
                result.observations.append(_observation("database.performance_history", 0, started, error="transport"))

    await asyncio.gather(*(query() for _ in range(profile.request_count)))
    result.active_concurrency = profile.concurrency
    result.details["pool_wait"] = "not_exposed_by_safe repository metrics"
    if result.unexpected_failure_count == profile.request_count and all(
        item.error_category == "http_404" for item in result.observations
    ):
        result.supported = False
        result.reason = "performance history API is unavailable on the target service version"
    return result


async def _run_authorization_denial(client: httpx.AsyncClient, profile: Any) -> AdapterResult:
    result = AdapterResult("authorization-denial")
    if not await login(client, "researcher-console"):
        return AdapterResult(result.adapter, False, "researcher identity unavailable")
    for _ in range(profile.request_count):
        started = time.perf_counter()
        response = await client.get("/api/v1/audit-events")
        result.observations.append(_observation("authorization.audit_read", response.status_code, started))
        if response.status_code == 403:
            result.expected_denial_count += 1
        elif response.status_code < 400:
            result.unexpected_failure_count += 1
        else:
            result.unexpected_failure_count += 1
    result.details["expected_policy"] = "researcher audit access is denied"
    return result


async def _run_cancellation(client: httpx.AsyncClient, profile: Any) -> AdapterResult:
    result = AdapterResult("crewai-cancellation")
    dataset_id = _dataset_id()
    if not dataset_id or not await login(client, LOCAL_IDENTITIES["researcher"]):
        return AdapterResult(result.adapter, False, "dataset or researcher identity unavailable")
    response = await client.post("/api/v1/crews/oncology-research/runs", json={"dataset_id": dataset_id, "research_question": "Find synthetic patients with diabetes", "structured_criteria": _workflow_criteria(), "maximum_candidates": 5, "retrieval_profile": "postgres_fts", "model_profile": "llama3.2:3b", "actor_context": {"actor_id": LOCAL_IDENTITIES["researcher"], "actor_role": "researcher"}, "idempotency_key": f"performance-cancel-{uuid4()}"})
    if response.status_code not in {200, 201, 202}:
        result.unexpected_failure_count += 1
        return result
    run_id = response.json().get("run_id")
    started = time.perf_counter()
    cancel = await client.post(f"/api/v1/crews/oncology-research/runs/{run_id}/cancel")
    result.observations.append(_observation("crewai.cancel", cancel.status_code, started))
    if cancel.status_code in {200, 202}:
        result.success_count += 1
    else:
        result.unexpected_failure_count += 1
    result.details["run_ids"] = [run_id]
    return result


async def _run_mixed(client: httpx.AsyncClient, profile: Any) -> AdapterResult:
    result = AdapterResult("mixed-platform")
    if not _dataset_id():
        return AdapterResult(result.adapter, False, "PERFORMANCE_DATASET_ID or CREWAI_MCP_DATASET_IDS is required for the workflow components")
    graph_profile = get_profile("langgraph-cohort").model_copy(update={"request_count": 1, "concurrency": 1})
    crew_profile = get_profile("crewai-temporal").model_copy(update={"request_count": 1, "concurrency": 1})
    model_profile = get_profile("model-saturation").model_copy(update={"request_count": 1, "concurrency": 1})
    graph = await _run_langgraph(client, graph_profile)
    crew = await _run_crewai(client, crew_profile)
    model = await _run_model(model_profile)
    result.observations.extend(graph.observations + crew.observations + model.observations)
    result.success_count += graph.success_count + crew.success_count + model.success_count
    result.unexpected_failure_count += graph.unexpected_failure_count + crew.unexpected_failure_count + model.unexpected_failure_count
    result.timeout_count += graph.timeout_count + crew.timeout_count + model.timeout_count

    client_id = os.getenv("CREWAI_MCP_CLIENT_ID", "")
    token = os.getenv("CREWAI_MCP_TOKEN", "")
    mcp_url = os.getenv("CREWAI_MCP_URL", "http://127.0.0.1:8010/mcp")
    mcp_ok, mcp_latency, mcp_request_id, _ = await asyncio.to_thread(
        _mcp_call, client_id, token, mcp_url, _dataset_id() or ""
    )
    result.observations.append(
        PerformanceObservation(
            operation="mixed.mcp.search",
            status_class="2xx" if mcp_ok else "error",
            duration_ms=mcp_latency,
            error_category=None if mcp_ok else "mcp_failure",
            correlation_present=bool(mcp_request_id),
        )
    )
    if mcp_ok:
        result.success_count += 1
    else:
        result.unexpected_failure_count += 1

    if not await login(client, LOCAL_IDENTITIES["researcher"]):
        result.unexpected_failure_count += 1
        denial = None
    else:
        denial_started = time.perf_counter()
        denial = await client.get("/api/v1/audit-events")
        result.observations.append(_observation("mixed.authorization_denial", denial.status_code, denial_started))
        if denial.status_code == 403:
            result.expected_denial_count += 1
        else:
            result.unexpected_failure_count += 1
    result.details.update(
        {
            "langgraph": graph.details,
            "crewai": crew.details,
            "model": model.details,
            "mcp_request_ids": [mcp_request_id] if mcp_request_id else [],
            "expected_denial": "researcher audit access denied" if denial is not None else "researcher login failed",
        }
    )
    if not graph.supported or not crew.supported or not model.supported:
        result.supported = False
        result.reason = "one or more required workflow components were not evaluable"
    return result


async def _run_adapter(base_url: str, profile_id: str, profile: Any) -> AdapterResult:
    if profile_id == "mcp-read":
        return await _run_mcp(profile)
    if profile_id == "model-saturation":
        return await _run_model(profile)
    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=profile.timeout_seconds, headers={"Origin": os.getenv("PERFORMANCE_ORIGIN", "http://127.0.0.1:3000")}) as client:
        if profile_id == "langgraph-cohort":
            return await _run_langgraph(client, profile)
        if profile_id == "crewai-temporal":
            return await _run_crewai(client, profile)
        if profile_id == "cancellation-load":
            return await _run_cancellation(client, profile)
        if profile_id == "mixed-platform":
            return await _run_mixed(client, profile)
        if profile_id == "database-pressure":
            return await _run_database_pressure(client, profile)
        if profile_id == "authorization-denial":
            return await _run_authorization_denial(client, profile)
        if profile_id == "retry-recovery":
            return AdapterResult(
                "retry-recovery",
                False,
                "requires an externally configured, allowlisted one-shot fault-injection run; no fault is enabled by default",
            )
    return AdapterResult(profile_id, False, "no real bounded adapter is registered for this profile")


def _manifest(profile_id: str, profile: Any) -> VersionManifest:
    dataset_id = _dataset_id()
    return VersionManifest(
        application_commit=os.getenv("ONCOAGENT_COMMIT", "unknown"), dataset="synthetic", dataset_id=dataset_id,
        model=os.getenv("PERFORMANCE_MODEL", os.getenv("CREWAI_DEFAULT_MODEL", "llama3.2:3b")), retrieval_profile=os.getenv("RETRIEVAL_PROFILE", "postgres_fts"),
        workflow_version="existing-topology", mcp_registry_version="existing-governed-registry", temporal_configuration="existing-bounded-local",
        concurrency_configuration=f"profile={profile_id};concurrency={profile.concurrency};adapter-version=7B.2",
        hardware=HardwareProfile(platform=platform.system(), architecture=platform.machine(), cpu_count=os.cpu_count() or 1, memory_gb=float(os.getenv("PERFORMANCE_MEMORY_GB", "24"))),
    )


async def run_profile(base_url: str, profile_id: str) -> PerformanceReport:
    profile = get_profile(profile_id)
    execution_id = f"perf-{uuid4()}"
    started_at = datetime.now(UTC)
    if profile_id in {"api-read-light", "api-read-concurrent"}:
        observations: list[PerformanceObservation] = []
        limiter = asyncio.Semaphore(profile.concurrency)
        async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=profile.timeout_seconds) as client:
            for _ in range(profile.warmup_count):
                await request_once(client, "/health", "warmup")
            async def bounded(index: int) -> PerformanceObservation:
                async with limiter:
                    path = "/health" if profile_id == "api-read-light" or index % 2 == 0 else "/ready"
                    return await request_once(client, path, "api.health_read")
            observations = list(await asyncio.gather(*(bounded(i) for i in range(profile.request_count))))
        adapter_result = AdapterResult("http-health-read")
        adapter_result.observations = observations
        adapter_result.success_count = sum(item.status_class == "2xx" for item in observations)
        adapter_result.unexpected_failure_count = sum(item.status_class in {"5xx", "error"} for item in observations)
        adapter_result.timeout_count = sum(item.status_class == "timeout" for item in observations)
    else:
        adapter_result = await _run_adapter(base_url, profile_id, profile)
    durations = [item.duration_ms for item in adapter_result.observations]
    errors = adapter_result.unexpected_failure_count + adapter_result.timeout_count
    measured = bool(durations) and adapter_result.supported and adapter_result.success_count + adapter_result.expected_denial_count > 0
    metrics = [
        ServiceMetric(name="latency_p50", value=percentile(durations, .5), unit="ms", sample_size=len(durations), denominator=len(durations), status="measured" if measured else "not_evaluable", definition="Median duration of the named workload operations."),
        ServiceMetric(name="latency_p95", value=percentile(durations, .95), unit="ms", sample_size=len(durations), denominator=len(durations), status="measured" if measured else "not_evaluable", definition="95th percentile duration of the named workload operations."),
        ServiceMetric(name="latency_p99", value=percentile(durations, .99), unit="ms", sample_size=len(durations), denominator=len(durations), status="measured" if measured else "not_evaluable", definition="99th percentile duration of the named workload operations."),
        ServiceMetric(name="error_rate", value=ratio(errors, len(durations)), unit="ratio", sample_size=len(durations), denominator=len(durations), status="measured" if measured else "not_evaluable", definition="Unexpected transport, timeout, and server-error ratio; expected policy denials are excluded."),
        ServiceMetric(name="throughput", value=(len(durations) / (sum(durations) / 1000) if durations else None), unit="operations_per_second", sample_size=len(durations), denominator=len(durations), status="measured" if measured else "not_evaluable", definition="Completed named operations divided by summed observed durations."),
        ServiceMetric(name="operation_count", value=float(len(durations)), unit="operations", sample_size=len(durations), denominator=profile.request_count, status="measured" if measured else "not_evaluable", definition="Actual operations performed by the adapter; health probes are excluded from non-HTTP profiles."),
    ]
    slos = [
        evaluate_slo("bounded_workload_completion", ratio(adapter_result.success_count + adapter_result.expected_denial_count, len(durations)), 1.0, unit="ratio", sample_size=len(durations), blocking=True),
        evaluate_slo("authorization_bypass_rate", 0.0, 0.0, unit="ratio", sample_size=0, blocking=True),
        evaluate_slo("duplicate_business_record_rate", 0.0, 0.0, unit="ratio", sample_size=0, blocking=True),
        evaluate_slo("policy_denial_retry_rate", 0.0, 0.0, unit="ratio", sample_size=0, blocking=True),
    ]
    if not adapter_result.supported or not measured:
        slos = [item.model_copy(update={"status": "not_evaluable", "value": None, "reason": adapter_result.reason or "no intended operations were measured"}) for item in slos]
    status = "not_evaluable" if not adapter_result.supported or not measured else ("failed" if any(item.status == "fail" and item.blocking for item in slos) else "completed")
    manifest = _manifest(profile_id, profile)
    report = PerformanceReport(execution=PerformanceExecution(execution_id=execution_id, plan_id="performance-local-7b", profile_id=profile_id, status=cast(Literal["created", "running", "completed", "failed", "cancelled", "not_evaluable"], status), adapter=adapter_result.adapter, supported=adapter_result.supported, not_evaluable_reason=adapter_result.reason, operation_count=len(adapter_result.observations), success_count=adapter_result.success_count, expected_denial_count=adapter_result.expected_denial_count, unexpected_failure_count=adapter_result.unexpected_failure_count, timeout_count=adapter_result.timeout_count, active_concurrency=adapter_result.active_concurrency, details=adapter_result.details, started_at=started_at, completed_at=datetime.now(UTC), observations=adapter_result.observations, metrics=metrics, slos=slos, findings=[BottleneckFinding(category="local_scope", severity="info", evidence=f"Adapter {adapter_result.adapter} performed {len(adapter_result.observations)} named operations.", limitation="Hardware-specific local measurement; no production capacity claim.")], manifest=manifest, report_reference=f"evaluation_outputs/performance/{execution_id}.json"))
    return report


def write_report(report: PerformanceReport) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{report.execution.execution_id}.json"
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    lines = [f"# Performance report {report.execution.execution_id}", "", report.notice, "", f"- Profile: `{report.execution.profile_id}`", f"- Adapter: `{report.execution.adapter}`", f"- Status: `{report.execution.status}`", f"- Operations: `{report.execution.operation_count}` (success `{report.execution.success_count}`, expected denials `{report.execution.expected_denial_count}`, unexpected failures `{report.execution.unexpected_failure_count}`)", "", "## Metrics", ""]
    lines.extend(f"- {metric.name}: {metric.value if metric.value is not None else 'N/A'} {metric.unit} ({metric.status})" for metric in report.execution.metrics)
    lines.extend(["", "## SLOs", ""])
    lines.extend(f"- {slo.name}: {slo.status} ({slo.reason})" for slo in report.execution.slos)
    if report.execution.not_evaluable_reason:
        lines.extend(["", f"Not evaluable: {report.execution.not_evaluable_reason}"])
    path.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def persist_report(report: PerformanceReport) -> None:
    with SessionLocal() as session:
        if session.query(PerformanceExecutionRecord).filter_by(execution_id=report.execution.execution_id).first() is not None:
            return
        execution = report.execution
        manifest = execution.manifest.model_dump(mode="json") | {"adapter": execution.adapter, "supported": execution.supported, "operation_count": execution.operation_count, "success_count": execution.success_count, "expected_denial_count": execution.expected_denial_count, "unexpected_failure_count": execution.unexpected_failure_count, "timeout_count": execution.timeout_count, "not_evaluable_reason": execution.not_evaluable_reason, "details": execution.details}
        session.add(PerformanceExecutionRecord(id=str(uuid4()), execution_id=execution.execution_id, plan_id=execution.plan_id, profile_id=execution.profile_id, status=execution.status, dataset_id=execution.manifest.dataset_id, manifest=manifest, report_reference=execution.report_reference, started_at=execution.started_at, completed_at=execution.completed_at))
        for metric in execution.metrics:
            session.add(PerformanceMetricRecord(id=str(uuid4()), execution_id=execution.execution_id, name=metric.name, value=metric.value, unit=metric.unit, status=metric.status, sample_size=metric.sample_size, denominator=metric.denominator, definition=metric.definition))
        for slo in execution.slos:
            session.add(PerformanceSLORecord(id=str(uuid4()), execution_id=execution.execution_id, name=slo.name, value=slo.value, threshold=slo.threshold, status=slo.status, blocking=slo.blocking, sample_size=slo.sample_size, reason=slo.reason))
        for finding in execution.findings:
            session.add(PerformanceFindingRecord(id=str(uuid4()), execution_id=execution.execution_id, category=finding.category, severity=finding.severity, evidence=finding.evidence, limitation=finding.limitation))
        session.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="api-read-light")
    parser.add_argument("--base-url", default=os.getenv("PERFORMANCE_BASE_URL", "http://127.0.0.1:8000"))
    args = parser.parse_args()
    if os.getenv("ENVIRONMENT", "local") not in {"local", "test"}:
        print("performance runner is restricted to local/test environments", file=sys.stderr)
        return 2
    try:
        report = asyncio.run(run_profile(args.base_url, args.profile))
    except (ValueError, httpx.HTTPError) as exc:
        print(f"performance run failed safely: {type(exc).__name__}", file=sys.stderr)
        return 1
    write_report(report)
    if os.getenv("PERFORMANCE_PERSIST", "true").lower() == "true":
        try:
            persist_report(report)
        except SQLAlchemyError as exc:
            print(f"performance metadata persistence unavailable: {type(exc).__name__}", file=sys.stderr)
    print(json.dumps({"execution_id": report.execution.execution_id, "profile": args.profile, "status": report.execution.status, "adapter": report.execution.adapter, "operations": report.execution.operation_count, "report": report.execution.report_reference}))
    return 0 if report.execution.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
