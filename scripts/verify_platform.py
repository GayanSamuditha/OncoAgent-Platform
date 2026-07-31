#!/usr/bin/env python3
"""Bounded, read-only local platform verification.

The checker reports service names and HTTP status only. It never prints
cookies, tokens, headers, database URLs, prompts, or clinical payloads.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    url: str | None = None
    port: int | None = None
    optional: bool = False


def http_status(url: str) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": "oncoagent-platform-check/1"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status


def tcp_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def main() -> int:
    require_optional = os.getenv("VERIFY_PLATFORM_REQUIRE_OPTIONAL", "0") == "1"
    api_base = os.getenv("PLATFORM_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    web_base = os.getenv("PLATFORM_WEB_BASE_URL", "http://127.0.0.1:3000").rstrip("/")
    api_origin = os.getenv("PLATFORM_WEB_ORIGIN", web_base)
    port = lambda name, default: int(os.getenv(name, str(default)))
    checks = [
        Check("api-health", f"{api_base}/health"),
        Check("api-ready", f"{api_base}/ready"),
        Check("frontend", web_base),
        Check("mcp-port", port=port("MCP_HOST_PORT", 8010)),
        Check("postgres-port", port=port("POSTGRES_HOST_PORT", 55432)),
        Check("temporal-frontend", port=port("TEMPORAL_HOST_PORT", 7233), optional=True),
        Check("temporal-ui", f"http://127.0.0.1:{port('TEMPORAL_UI_HOST_PORT', 8233)}", optional=True),
        Check("ollama", f"{os.getenv('LOCAL_LLM_BASE_URL', 'http://127.0.0.1:11434').rstrip('/')}/api/tags", optional=True),
        Check("otel-collector", f"http://127.0.0.1:{port('OTEL_HEALTH_HOST_PORT', 13133)}/", optional=True),
        Check("prometheus", f"http://127.0.0.1:{port('PROMETHEUS_HOST_PORT', 9090)}/-/ready", optional=True),
        Check("tempo", f"http://127.0.0.1:{port('TEMPO_HOST_PORT', 3200)}/ready", optional=True),
        Check("grafana", f"http://127.0.0.1:{port('GRAFANA_HOST_PORT', 3001)}/api/health", optional=True),
    ]
    results: list[dict[str, object]] = []
    failed = False
    for check in checks:
        ok = False
        detail = "unreachable"
        try:
            if check.url:
                status = http_status(check.url)
                ok = 200 <= status < 400
                detail = f"http_{status}"
            else:
                ok = tcp_open("127.0.0.1", check.port or 0)
                detail = "tcp_open" if ok else "tcp_closed"
        except (OSError, urllib.error.URLError, ValueError) as exc:
            detail = type(exc).__name__
        results.append({"service": check.name, "ok": ok, "detail": detail, "optional": check.optional})
        if not ok and (not check.optional or require_optional):
            failed = True

    # Keep the development session in memory only; never print or persist it.
    try:
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        login = urllib.request.Request(
            f"{api_base}/api/v1/auth/login",
            data=json.dumps({"user_key": "researcher-console"}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "oncoagent-platform-check/1", "Origin": api_origin},
            method="POST",
        )
        with opener.open(login, timeout=5) as response:
            login_ok = response.status == 200
        for name, url in (
            ("identity-login", None),
            ("identity-me", f"{api_base}/api/v1/auth/me"),
            ("release-gate-api", f"{api_base}/api/v1/release-policy"),
        ):
            ok = login_ok
            detail = "http_200" if ok else "login_failed"
            if url and ok:
                try:
                    with opener.open(url, timeout=5) as response:
                        ok = response.status == 200
                        detail = f"http_{response.status}"
                except (OSError, urllib.error.URLError) as exc:
                    ok = False
                    detail = type(exc).__name__
            results.append({"service": name, "ok": ok, "detail": detail, "optional": False})
            failed = failed or not ok
        try:
            with opener.open(f"{api_base}/api/v1/identity/users", timeout=5) as response:
                researcher_denied = response.status == 403
        except urllib.error.HTTPError as exc:
            researcher_denied = exc.code == 403
        results.append({"service": "researcher-admin-denial", "ok": researcher_denied, "detail": "http_403" if researcher_denied else "unexpected", "optional": False})
        failed = failed or not researcher_denied
    except (OSError, urllib.error.URLError, ValueError) as exc:
        results.append({"service": "identity-login", "ok": False, "detail": type(exc).__name__, "optional": False})
        failed = True

    print(json.dumps({"checks": results, "required_optional": require_optional}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
