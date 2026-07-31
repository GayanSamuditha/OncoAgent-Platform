"""Prepare the ignored local demo environment without exposing its service token."""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / ".env.demo"
EXAMPLE = ROOT / ".env.demo.example"
CLIENT_ID = "crewai-oncology-research"
DATASET_ID = "6b15ce38-e12c-4482-866e-59d333952024"


def _replace(lines: list[str], key: str, value: str) -> None:
    prefix = f"{key}="
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{prefix}{value}"
            return
    lines.append(f"{prefix}{value}")


def main() -> int:
    if not TARGET.exists():
        TARGET.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    current = dotenv_values(TARGET)
    token = str(current.get("CREWAI_MCP_TOKEN") or "").strip()
    if not token:
        token = secrets.token_urlsafe(48)
    registry = json.dumps(
        [
            {
                "client_id": CLIENT_ID,
                "token": token,
                "actor_id": CLIENT_ID,
                "actor_role": "researcher",
                "client_type": "service",
                "dataset_ids": [DATASET_ID],
            }
        ],
        separators=(",", ":"),
    )
    lines = [
        line
        for line in TARGET.read_text(encoding="utf-8").splitlines()
        if not line.startswith("NEXT_PUBLIC_API_BASE_URL=")
    ]
    values = {
        "CREWAI_MCP_CLIENT_ID": CLIENT_ID,
        "CREWAI_MCP_URL": "http://mcp:8010/mcp",
        "CREWAI_MCP_TOKEN": token,
        "CREWAI_MCP_DATASET_IDS": DATASET_ID,
        "MCP_DEV_CLIENTS": registry,
        "BACKEND_API_ORIGIN": "http://api:8000",
        "CORS_ORIGINS": '["http://127.0.0.1:3000"]',
        "DEMO_API_BASE": "http://127.0.0.1:8000",
        "DEMO_WEB_BASE": "http://127.0.0.1:3000",
        "PLAYWRIGHT_BASE_URL": "http://127.0.0.1:3000",
        "PERFORMANCE_ORIGIN": "http://127.0.0.1:3000",
        "PHASE6A_WEB_ORIGIN": "http://127.0.0.1:3000",
        "IDENTITY_COOKIE_SECURE": "false",
        "LOADTEST_RESEARCHER_IDENTITY": "researcher-console",
        "LOADTEST_REVIEWER_IDENTITY": "reviewer-console",
        "LOADTEST_OPERATOR_IDENTITY": "operator-console",
        "LOADTEST_ADMIN_IDENTITY": "admin-console",
        "LOADTEST_GOVERNANCE_IDENTITY": "governance-console",
    }
    for key, value in values.items():
        _replace(lines, key, value)
    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    TARGET.chmod(0o600)
    print("Prepared ignored .env.demo; service credential omitted from output.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
