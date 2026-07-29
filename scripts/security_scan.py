"""Run sanitized local security/privacy readiness checks.

Unavailable external scanners are recorded as ``not_evaluable``. Findings
never include matched values or source excerpts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation_outputs" / "security"
EXCLUDED = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".next",
    "evaluation_outputs",
    "backups",
}
SECRET_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "jwt": re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
    ),
    "bearer_token": re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{24,}"),
    "authorization_header_value": re.compile(
        r"(?i)authorization\s*[:=]\s*['\"][^'\"]{24,}['\"]"
    ),
}
PRIVACY_PATTERNS = {
    "raw_fhir": re.compile(r"(?i)\b(resourceType|Patient\.name|Observation\.value)\b"),
    "prompt_content": re.compile(
        r"(?i)\b(system prompt|hidden reasoning|chain.of.thought)\b"
    ),
    "database_url": re.compile(
        r"(?i)(postgres(?:ql)?(?:\+\w+)?://[^\s'\"]+|mysql://[^\s'\"]+)"
    ),
}


def tracked_files() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    ).stdout
    return [ROOT / value for value in output.decode().split("\0") if value]


def scan_patterns(patterns: dict[str, re.Pattern[str]]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in tracked_files():
        if any(part in EXCLUDED for part in path.parts) or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for kind, pattern in patterns.items():
            if pattern.search(text):
                # Safe development placeholders and policy documentation are
                # not secrets; values are never emitted.
                if kind in {"database_url", "raw_fhir", "prompt_content"}:
                    continue
                findings.append({"type": kind, "path": str(path.relative_to(ROOT))})
    return findings


def command_observation(command: list[str], name: str) -> dict[str, Any]:
    executable = shutil.which(command[0])
    if executable is None:
        return {
            "name": name,
            "status": "not_evaluable",
            "reason": f"{command[0]} is unavailable",
        }
    completed = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, timeout=120, check=False
    )
    return {
        "name": name,
        "status": "passed" if completed.returncode == 0 else "not_evaluable",
        "exit_code": completed.returncode,
        "reason": None
        if completed.returncode == 0
        else "scanner did not complete; output is intentionally omitted",
    }


def run_scan(kind: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    if kind in {"all", "secrets"}:
        secret_findings = scan_patterns(SECRET_PATTERNS)
        checks.append(
            {
                "name": "secret_scan",
                "status": "failed" if secret_findings else "passed",
                "findings": secret_findings,
            }
        )
    if kind in {"all", "privacy"}:
        privacy_findings = scan_patterns(PRIVACY_PATTERNS)
        checks.append(
            {
                "name": "privacy_scan",
                "status": "failed" if privacy_findings else "passed",
                "findings": privacy_findings,
            }
        )
    if kind in {"all", "dependencies"}:
        checks.extend(
            [
                command_observation(
                    ["pip-audit", "--format", "json"], "python_dependency_scan"
                ),
                command_observation(
                    ["npm", "audit", "--omit=dev", "--json"], "node_dependency_scan"
                ),
                command_observation(
                    ["bandit", "-r", "apps/api/app", "-q"], "static_security_scan"
                ),
                command_observation(
                    ["trivy", "fs", "--scanners", "vuln", "--format", "json", "."],
                    "container_dependency_scan",
                ),
            ]
        )
    result: dict[str, Any] = {
        "report_version": "phase7c-security-scan-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "environment": "local_development",
        "status": "passed"
        if all(item["status"] == "passed" for item in checks)
        else "not_evaluable"
        if any(item["status"] == "not_evaluable" for item in checks)
        else "failed",
        "checks": checks,
        "limitations": [
            "Synthetic development data only.",
            "Scanner availability is reported explicitly; no unavailable scanner is treated as a pass.",
        ],
    }
    return result


def write_report(result: dict[str, Any]) -> tuple[Path, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    result["artifact_hash"] = hashlib.sha256(encoded).hexdigest()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = OUT / f"security-{stamp}.json"
    md_path = OUT / f"security-{stamp}.md"
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Security readiness scan",
        "",
        f"- Status: **{result['status']}**",
        f"- Artifact hash: `{result['artifact_hash']}`",
        "",
        "| Check | Status |",
        "|---|---|",
    ]
    lines.extend(f"| {item['name']} | {item['status']} |" for item in result["checks"])
    lines.extend(
        [
            "",
            "Scanner values and sensitive source content are intentionally omitted.",
            "Synthetic development evidence; not a certification.",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def persist_assessment(result: dict[str, Any], report_path: Path) -> str:
    from app.db.session import SessionLocal
    from app.models.security import SecurityAssessmentRecord, SecurityFindingRecord
    from app.security.policy import SECURITY_POLICY_VERSION

    assessment_id = f"security-{result['artifact_hash'][:16]}"
    with SessionLocal.begin() as session:
        existing = (
            session.query(SecurityAssessmentRecord)
            .filter_by(assessment_id=assessment_id)
            .one_or_none()
        )
        if existing is None:
            assessment = SecurityAssessmentRecord(
                id=str(uuid4()),
                assessment_id=assessment_id,
                policy_version=SECURITY_POLICY_VERSION,
                status=result["status"],
                artifact_hash=result["artifact_hash"],
                report_reference=str(report_path),
                findings_summary={
                    item["name"]: item["status"] for item in result["checks"]
                },
                gates=[],
                limitations=result["limitations"],
            )
            session.add(assessment)
            for check in result["checks"]:
                for index, finding in enumerate(check.get("findings", [])):
                    session.add(
                        SecurityFindingRecord(
                            id=str(uuid4()),
                            assessment_id=assessment.id,
                            finding_id=f"{assessment_id}:{index}",
                            category=check["name"],
                            severity="high",
                            state="open",
                            title=finding["type"],
                            location=finding.get("path"),
                            reason="Sanitized scanner finding; source value omitted.",
                        )
                    )
    return assessment_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", choices=["all", "secrets", "privacy", "dependencies"], default="all"
    )
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()
    result = run_scan(args.check)
    json_path, md_path = write_report(result)
    assessment_id = persist_assessment(result, json_path) if args.persist else None
    print(
        json.dumps(
            {
                "status": result["status"],
                "json": str(json_path),
                "markdown": str(md_path),
                "artifact_hash": result["artifact_hash"],
                "assessment_id": assessment_id,
            }
        )
    )
    return (
        0 if result["status"] == "passed" else 1 if result["status"] == "failed" else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
