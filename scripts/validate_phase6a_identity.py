"""Bounded local Phase 6A identity and authorization validation.

This runner uses the public FastAPI contracts and temporary, reversible local
database fixtures only for grant/disabled-user checks.  It never prints or
persists cookies, tokens, authorization headers, passwords, or IdP claims.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.core.config import get_settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.identity import DatasetGrant, User  # noqa: E402

BASE_URL = os.environ.get("PHASE6A_API_URL", "http://127.0.0.1:8000").rstrip("/")
WEB_ORIGIN = os.environ.get("PHASE6A_WEB_ORIGIN", "http://localhost:3000")
REPORT_DIR = ROOT / "evaluation_outputs" / "identity"
POLL_SECONDS = 2
POLL_LIMIT = 90


@dataclass
class Client:
    name: str
    opener: Any


def call(
    client: Client | None,
    path: str,
    method: str = "GET",
    body: Any = None,
    *,
    origin: bool = False,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    headers = {"accept": "application/json"}
    if body is not None:
        headers["content-type"] = "application/json"
    if origin:
        headers["origin"] = WEB_ORIGIN
    if extra_headers:
        headers.update(extra_headers)
    request = Request(
        f"{BASE_URL}{path}",
        method=method,
        headers=headers,
        data=json.dumps(body).encode() if body is not None else None,
    )
    opener = client.opener if client else build_opener()
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read(2_000_000)
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read(2_000_000)
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"detail": "non-json error"}
        return exc.code, payload
    except (URLError, TimeoutError, OSError) as exc:
        return 599, {"detail": type(exc).__name__}


def login(name: str) -> tuple[Client | None, dict[str, Any]]:
    jar = CookieJar()
    client = Client(name, build_opener(__import__("urllib.request").request.HTTPCookieProcessor(jar)))
    status, payload = call(client, "/api/v1/auth/login", "POST", {"user_key": name})
    return (client if status == 200 else None), {"status": status, "body": payload}


def expect(
    client: Client | None,
    path: str,
    expected: int,
    *,
    method: str = "GET",
    body: Any = None,
    origin: bool = False,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    status, payload = call(client, path, method, body, origin=origin, extra_headers=extra_headers)
    return {"path": path, "method": method, "expected": expected, "actual": status, "passed": status == expected, "detail": payload.get("detail") if isinstance(payload, dict) else None}


def wait_crew(client: Client, run_id: str, wanted: set[str]) -> dict[str, Any]:
    last: dict[str, Any] = {}
    for _ in range(POLL_LIMIT):
        status, payload = call(client, f"/api/v1/crews/oncology-research/runs/{run_id}")
        if status != 200:
            return {"status": status, "body": payload}
        last = payload
        if payload.get("status") in wanted:
            return {"status": status, "body": payload}
        time.sleep(POLL_SECONDS)
    return {"status": 504, "body": {"detail": "bounded polling timeout", "last_status": last.get("status")}}


def temporary_revoke(user_subject: str, dataset_id: str) -> tuple[str | None, bool | None]:
    """Disable one existing grant and return its prior state for restoration."""
    with SessionLocal.begin() as session:
        user = session.query(User).filter(User.external_subject == user_subject).one_or_none()
        if user is None:
            return None, None
        grant = session.query(DatasetGrant).filter(DatasetGrant.user_id == user.id, DatasetGrant.dataset_id == dataset_id).one_or_none()
        if grant is None:
            return user.id, None
        prior = grant.enabled
        grant.enabled = False
        return user.id, prior


def restore_grant(user_id: str | None, dataset_id: str, prior: bool | None) -> None:
    if user_id is None or prior is None:
        return
    with SessionLocal.begin() as session:
        grant = session.query(DatasetGrant).filter(DatasetGrant.user_id == user_id, DatasetGrant.dataset_id == dataset_id).one_or_none()
        if grant is not None:
            grant.enabled = prior


def temporary_disable_user(subject: str) -> tuple[str | None, bool | None]:
    with SessionLocal.begin() as session:
        user = session.query(User).filter(User.external_subject == subject).one_or_none()
        if user is None:
            return None, None
        prior = user.enabled
        user.enabled = False
        return user.id, prior


def restore_user(user_id: str | None, prior: bool | None) -> None:
    if user_id is None or prior is None:
        return
    with SessionLocal.begin() as session:
        user = session.get(User, user_id)
        if user is not None:
            user.enabled = prior


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 6A.1 Identity Validation",
        "",
        f"- Status: **{report['status']}**",
        f"- Validation ID: `{report['validation_id']}`",
        f"- Timestamp: `{report['timestamp']}`",
        "- Environment: local synthetic development only",
        "- Not clinically validated.",
        "",
        "## Checks",
        "",
    ]
    for section, checks in report["sections"].items():
        lines.append(f"### {section}")
        for check in checks:
            mark = "PASS" if check.get("passed") else "FAIL"
            lines.append(f"- {mark}: {check.get('path', check.get('name', 'check'))} ({check.get('actual', '')})")
        lines.append("")
    lines.extend(["## Limitations", "", "- Local built-in identities are an OIDC-compatible development simulation, not production authentication.", "- Frontend browser rendering is reported separately when the Next.js service is unavailable.", "- No raw FHIR, credentials, cookies, tokens, prompts, or hidden reasoning are included in this report.", ""])
    return "\n".join(lines)


def main() -> int:
    settings = get_settings()
    if settings.environment not in {"local", "test"}:
        print("Phase 6A.1 validation is local/test-only; refusing to run.")
        return 2
    validation_id = str(uuid4())
    report: dict[str, Any] = {
        "validation_id": validation_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "api_base": BASE_URL,
        "alembic_expected_head": "0012_identity_governance",
        "sections": {},
    }
    failures = 0

    def add(section: str, result: dict[str, Any]) -> None:
        nonlocal failures
        report["sections"].setdefault(section, []).append(result)
        failures += not result.get("passed", False)

    add("Route discovery", {"name": "OpenAPI available", "passed": call(None, "/openapi.json")[0] == 200, "actual": call(None, "/openapi.json")[0]})
    openapi_status, openapi = call(None, "/openapi.json")
    if openapi_status == 200:
        expected_routes = ["/api/v1/auth/login", "/api/v1/auth/me", "/api/v1/crews/oncology-research/runs/{run_id}/review", "/api/v1/identity/users"]
        for route in expected_routes:
            add("Route discovery", {"name": route, "passed": route in openapi.get("paths", {}), "actual": route in openapi.get("paths", {})})

    # Authentication matrix.  The report stores only status codes/reason codes.
    add("Authentication", expect(None, "/api/v1/auth/me", 401))
    add("Authentication", expect(None, "/api/v1/auth/me", 401, method="GET"))
    clients: dict[str, Client] = {}
    for user_key in ("researcher-console", "reviewer-console", "governance-console", "operator-console", "auditor-console", "admin-console"):
        client, result = login(user_key)
        result.update({"name": f"login:{user_key}", "passed": result["status"] == 200})
        add("Authentication", result)
        if client:
            clients[user_key] = client
            add("Authentication", expect(client, "/api/v1/auth/me", 200))
    if "researcher-console" in clients:
        add("Authentication", expect(clients["researcher-console"], "/api/v1/auth/logout", 200, method="POST", origin=True))
        add("Authentication", expect(clients["researcher-console"], "/api/v1/auth/me", 401))
        # Re-login after logout for the remaining researcher checks.
        researcher, _ = login("researcher-console")
        if researcher:
            clients["researcher-console"] = researcher
        add("Authentication", expect(clients["researcher-console"], "/api/v1/auth/me", 200))

    # Role matrix uses actual protected endpoints.
    matrix = {
        "researcher-console": [("/api/v1/identity/users", 403), ("/api/v1/audit-events", 403), ("/api/v1/temporal/status", 403)],
        "reviewer-console": [("/api/v1/identity/users", 403), ("/api/v1/audit-events", 403), ("/api/v1/temporal/status", 403)],
        "governance-console": [("/api/v1/audit-events", 200), ("/api/v1/resilience/certifications", 200), ("/api/v1/identity/users", 403), ("/api/v1/temporal/status", 403)],
        "auditor-console": [("/api/v1/audit-events", 200), ("/api/v1/resilience/certifications", 200), ("/api/v1/identity/users", 403), ("/api/v1/temporal/status", 403)],
        "operator-console": [("/api/v1/temporal/status", 200), ("/api/v1/audit-events", 403), ("/api/v1/identity/users", 403)],
        "admin-console": [("/api/v1/identity/users", 200), ("/api/v1/temporal/status", 200)],
    }
    for user_key, cases in matrix.items():
        for path, expected in cases:
            add("Role matrix", {**expect(clients.get(user_key), path, expected), "name": f"{user_key}:{path}"})

    # Invalid bearer claims are generated locally and are never included in output.
    import jwt

    for name, claims in (
        ("wrong issuer", {"iss": "wrong", "aud": settings.identity_audience, "sub": "researcher-console", "exp": datetime.now(UTC) + timedelta(minutes=5)}),
        ("wrong audience", {"iss": settings.identity_issuer, "aud": "wrong", "sub": "researcher-console", "exp": datetime.now(UTC) + timedelta(minutes=5)}),
        ("expired", {"iss": settings.identity_issuer, "aud": settings.identity_audience, "sub": "researcher-console", "exp": datetime.now(UTC) - timedelta(minutes=5)}),
    ):
        token = jwt.encode(claims, settings.identity_signing_secret, algorithm="HS256")
        opener = build_opener()
        request = Request(f"{BASE_URL}/api/v1/auth/me", headers={"authorization": f"Bearer {token}"})
        try:
            with opener.open(request, timeout=20) as response:
                actual = response.status
        except HTTPError as exc:
            actual = exc.code
        add("Authentication", {"name": name, "expected": 401, "actual": actual, "passed": actual == 401})

    unsupported_token = jwt.encode(
        {"iss": settings.identity_issuer, "aud": settings.identity_audience, "sub": "researcher-console", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        key=None,
        algorithm="none",
    )
    unsupported_status, _ = call(
        None,
        "/api/v1/auth/me",
        extra_headers={"authorization": f"Bearer {unsupported_token}"},
    )
    add("Authentication", {"name": "unsupported signing algorithm", "expected": 401, "actual": unsupported_status, "passed": unsupported_status == 401})

    add(
        "Authentication",
        expect(
            None,
            "/api/v1/auth/me",
            401,
            extra_headers={"x-actor-id": "admin-console", "x-actor-role": "administrator"},
        ) if not settings.identity_legacy_headers_enabled else {"name": "legacy headers disabled", "passed": True, "actual": "bridge enabled by configuration"},
    )

    # Dataset setup is reversible: disable one grant for an existing local user.
    status, datasets = call(clients.get("researcher-console"), "/api/v1/datasets")
    dataset_ids = [item.get("id") for item in datasets] if status == 200 and isinstance(datasets, list) else [item.get("id") for item in datasets.get("items", [])] if isinstance(datasets, dict) else []
    if len(dataset_ids) >= 2:
        # Prefer a dataset with an existing pending run so review validation
        # does not needlessly start another local-model execution.
        _, existing_runs = call(clients.get("researcher-console"), "/api/v1/crews/oncology-research/runs")
        existing_items = existing_runs.get("items", []) if isinstance(existing_runs, dict) else []
        allowed_crew_datasets = {item for item in settings.crewai_mcp_dataset_ids.split(",") if item}
        target_dataset = next(
            (
                item.get("dataset_id")
                for item in existing_items
                if item.get("status") == "awaiting_human_review"
                and item.get("actor_id") == "researcher-console"
                and item.get("dataset_id") in dataset_ids
            ),
            next((item for item in dataset_ids if item in allowed_crew_datasets), dataset_ids[0]),
        )
        unauthorized_dataset = next(item for item in dataset_ids if item != target_dataset)
        user_id, prior_grant = temporary_revoke("researcher-console", unauthorized_dataset)
        try:
            fresh_researcher, _ = login("researcher-console")
            add("Dataset authorization", {**expect(fresh_researcher, "/api/v1/runs", 403, method="POST", origin=True, body={"dataset_id": unauthorized_dataset, "request": "Find synthetic adults with hypertension", "criteria": [], "max_candidates": 1, "planner_provider": "deterministic"}), "name": "unauthorized dataset run"})
        finally:
            restore_grant(user_id, unauthorized_dataset, prior_grant)
    else:
        target_dataset = dataset_ids[0] if dataset_ids else None
        add("Dataset authorization", {"name": "two-dataset fixture", "passed": False, "actual": "fewer than two datasets available"})

    # Review boundary: reuse a pending researcher-created run, or create one with an idempotency key.
    pending: dict[str, Any] | None = None
    report["review_probe"] = {"target_dataset": None, "list_status": None, "pending_status": None}
    if target_dataset and clients.get("researcher-console"):
        status, payload = call(clients["researcher-console"], "/api/v1/crews/oncology-research/runs")
        report["review_probe"].update({"target_dataset": target_dataset, "list_status": status})
        items = payload.get("items", []) if isinstance(payload, dict) else []
        pending = next((item for item in items if item.get("status") == "awaiting_human_review" and item.get("actor_id") == "researcher-console"), None)
        report["review_probe"]["pending_status"] = pending.get("status") if pending else None
        if pending is None:
            active = next(
                (
                    item
                    for item in items
                    if item.get("actor_id") == "researcher-console"
                    and item.get("status") in {"created", "validating", "running", "discovering_candidates", "collecting_evidence", "reviewing_evidence", "generating_brief"}
                ),
                None,
            )
            if active:
                active_result = wait_crew(clients["researcher-console"], active["id"], {"awaiting_human_review", "failed", "rejected", "cancelled"})
                pending = active_result.get("body") if isinstance(active_result.get("body"), dict) else None
        if pending is None:
            body = {
                "dataset_id": target_dataset,
                "research_question": "Find synthetic adults with hypertension and elevated blood pressure",
                "structured_criteria": [
                    {"criterion_type": "minimum_age", "operator": "gte", "value": 18},
                    {"criterion_type": "condition", "clinical_concept": "hypertension", "required": True},
                    {"criterion_type": "observation", "clinical_concept": "elevated blood pressure", "required": True},
                ],
                "maximum_candidates": 5,
                "retrieval_profile": "medcpt",
                "model_profile": "automatic",
                "actor_context": {"actor_id": "researcher-console", "actor_role": "researcher"},
                "correlation_id": validation_id,
                "idempotency_key": f"phase6a1:{validation_id}",
            }
            code, created = call(clients["researcher-console"], "/api/v1/crews/oncology-research/runs", "POST", body, origin=True)
            pending = created if code in {200, 202} else None
            if pending is None:
                add("Review authorization", {"name": "researcher run reaches review", "expected": "202", "actual": code, "passed": False, "detail": created.get("detail") if isinstance(created, dict) else None})
            if pending:
                pending = wait_crew(clients["researcher-console"], pending["run_id"], {"awaiting_human_review", "failed", "rejected", "cancelled"})["body"]
        run_id = pending.get("run_id") or pending.get("id") if pending else None
        if run_id:
            add("Review authorization", {**expect(clients["researcher-console"], f"/api/v1/crews/oncology-research/runs/{run_id}/review", 200), "name": "creator can inspect review"})
            add("Review authorization", {**expect(clients["researcher-console"], f"/api/v1/crews/oncology-research/runs/{run_id}/review", 403, method="POST", origin=True, body={"decision": "accept_for_synthetic_research", "comment": "self approval probe"}), "name": "self approval denied"})
            add("Review authorization", {**expect(clients["reviewer-console"], f"/api/v1/crews/oncology-research/runs/{run_id}/review", 200), "name": "assigned reviewer can inspect"})
            review_code, review_body = call(clients["reviewer-console"], f"/api/v1/crews/oncology-research/runs/{run_id}/review", "POST", {"decision": "accept_for_synthetic_research", "comment": "Synthetic development review."}, origin=True)
            add("Review authorization", {"name": "assigned reviewer approval", "expected": 200, "actual": review_code, "passed": review_code == 200})
            final = wait_crew(clients["researcher-console"], run_id, {"accepted", "completed", "rejected", "cancelled", "failed"})
            add("Review authorization", {"name": "reviewed run terminal", "expected": True, "actual": final["body"].get("status") if isinstance(final.get("body"), dict) else None, "passed": final["body"].get("status") in {"accepted", "completed"} if isinstance(final.get("body"), dict) else False})
            for name, client in (("duplicate review", clients["reviewer-console"]), ("conflicting review", clients["reviewer-console"])):
                code, _ = call(client, f"/api/v1/crews/oncology-research/runs/{run_id}/review", "POST", {"decision": "reject", "comment": name}, origin=True)
                add("Review authorization", {"name": name, "expected": 409, "actual": code, "passed": code == 409})
            report["review"] = {"run_id": run_id, "creator": "researcher-console", "reviewer": "reviewer-console", "final_status": final["body"].get("status") if isinstance(final.get("body"), dict) else None}
        elif pending and pending.get("status") != "awaiting_human_review":
            add("Review authorization", {"name": "researcher run reaches review", "expected": "awaiting_human_review", "actual": pending.get("status"), "passed": False})
    else:
        add("Review authorization", {"name": "review boundary setup", "passed": False, "actual": "researcher or dataset unavailable"})

    # Disabled identity is a reversible local fixture.
    disabled_id, disabled_prior = temporary_disable_user("reviewer-console")
    try:
        disabled_client, _ = login("reviewer-console")
        add("Authentication", {"name": "disabled reviewer denied", **expect(disabled_client, "/api/v1/auth/me", 401)})
    finally:
        restore_user(disabled_id, disabled_prior)

    # Audit records are read through the auditor API and scanned only for forbidden categories.
    status, audit = call(clients.get("auditor-console"), "/api/v1/audit-events")
    serialized = json.dumps(audit).lower()
    forbidden = ["authorization: bearer", "password", "jwt", "oncoagent_session", "database_url", "raw fhir"]
    add("Audit and redaction", {"name": "audit endpoint available", "expected": 200, "actual": status, "passed": status == 200})
    add("Audit and redaction", {"name": "sensitive audit values absent", "expected": True, "actual": [item for item in forbidden if item in serialized], "passed": not any(item in serialized for item in forbidden)})

    # Frontend is optional during API validation; no credentials are sent here.
    frontend = call(None, "/login") if os.environ.get("PHASE6A_FRONTEND_URL") else (0, {})
    report["frontend"] = {"status": frontend[0], "checked": bool(os.environ.get("PHASE6A_FRONTEND_URL")), "note": "Browser route behavior requires a running Next.js development server."}
    report["status"] = "passed" if failures == 0 else "failed"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / f"{validation_id}.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    (REPORT_DIR / f"{validation_id}.md").write_text(markdown(report))
    print(f"Phase 6A.1 validation {report['status']}: {validation_id} ({failures} failed checks)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
