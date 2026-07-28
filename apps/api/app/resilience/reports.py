"""Safe local resilience report storage and Markdown rendering."""

import json
from pathlib import Path
from typing import Any

from app.resilience.contracts import CertificationReport

REPORT_DIR = Path(__file__).resolve().parents[4] / "evaluation_outputs" / "resilience"


def report_paths(certification_id: str) -> tuple[Path, Path]:
    return REPORT_DIR / f"{certification_id}.json", REPORT_DIR / f"{certification_id}.md"


def save_report(report: CertificationReport) -> tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path, markdown_path = report_paths(report.certification_id)
    json_path.write_text(report.model_dump_json(indent=2) + "\n")
    lines = [
        f"# Resilience certification {report.certification_id}",
        "",
        "Synthetic development validation; local-only and not clinically validated.",
        "",
        f"- Status: **{report.overall_status}**",
        f"- Registry: `{report.scenario_registry_version}`",
        f"- Generated: `{report.generated_at}`",
        "",
        "## Scenarios",
        "",
        "| Scenario | Status | Attempts | Audit | Trace | Result |",
        "|---|---|---:|---|---|---|",
    ]
    for item in report.scenarios:
        lines.append(f"| {item.scenario_id} | {item.final_status} | {item.activity_attempts} | {item.audit_result} | {item.trace_result} | {'PASS' if item.passed else 'FAIL'} |")
    lines.extend(["", "## Scorecard", ""])
    for name, gate in report.scorecard.items():
        lines.append(f"- `{name}`: `{gate.get('value')}` / threshold `{gate.get('threshold')}` — **{'PASS' if gate.get('passed') else 'FAIL'}**")
    if report.limitations:
        lines.extend(["", "## Limitations", "", *[f"- {item}" for item in report.limitations]])
    markdown_path.write_text("\n".join(lines) + "\n")
    return json_path, markdown_path


def load_reports() -> list[dict[str, Any]]:
    if not REPORT_DIR.exists():
        return []
    reports: list[dict[str, Any]] = []
    for path in sorted(REPORT_DIR.glob("*.json")):
        try:
            reports.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    # Consumers use the first item as the current certification.  Keep the
    # API deterministic while ensuring an older incomplete report cannot mask
    # a newer result.
    return sorted(reports, key=lambda item: str(item.get("generated_at", "")), reverse=True)
