import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from .contracts import MetricResult, MetricStatus, ReleaseCandidate, ReleaseEvaluationReport
from .policy import decide_release, detect_regressions, evaluate_gates

ROOT = Path(__file__).resolve().parents[4]
REPORT_DIR = ROOT / "evaluation_outputs" / "release"


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("evaluation artifact must be a JSON object")
    return loaded


def _metric(
    name: str,
    value: Any,
    definition: str,
    direction: Literal["higher", "lower", "none"],
    baseline: Any = None,
    sample_size: int = 0,
    denominator: int | None = None,
    applicable: bool = True,
) -> MetricResult:
    numeric = float(value) if isinstance(value, (int, float)) else None
    baseline_numeric = float(baseline) if isinstance(baseline, (int, float)) else None
    metric_status: MetricStatus = (
        "measured"
        if numeric is not None
        else "not_applicable"
        if not applicable
        else "not_evaluable"
    )
    return MetricResult(
        name=name,
        value=numeric,
        status=metric_status,
        applicable=applicable,
        sample_size=sample_size,
        denominator=denominator,
        definition=definition,
        direction=direction,
        baseline_value=baseline_numeric,
        delta=numeric - baseline_numeric
        if numeric is not None and baseline_numeric is not None
        else None,
        limitations=(
            []
            if numeric is not None
            else [
                "Metric is explicitly not applicable to this evaluation suite."
                if not applicable
                else "No measured candidate value was supplied."
            ]
        ),
    )


def normalize_metrics(
    candidate_data: Mapping[str, Any], baseline_data: Mapping[str, Any] | None
) -> tuple[list[MetricResult], dict[str, Any]]:
    candidate_metrics = candidate_data.get("metrics", candidate_data)
    not_applicable = candidate_data.get("not_applicable_metrics", [])
    if not isinstance(not_applicable, list):
        not_applicable = []
    baseline_metrics = baseline_data.get("metrics", baseline_data) if baseline_data else {}
    if not isinstance(candidate_metrics, Mapping):
        candidate_metrics = {}
    if not isinstance(baseline_metrics, Mapping):
        baseline_metrics = {}
    definitions: dict[str, tuple[str, Literal["higher", "lower", "none"]]] = {
        "unsafe_execution_rate": ("Unsafe instructions executed / unsafe scenarios.", "lower"),
        "policy_violation_prevention_rate": (
            "Prevented policy violations / applicable unsafe scenarios.",
            "higher",
        ),
        "human_review_compliance_rate": (
            "Runs requiring review that enforced review / applicable runs.",
            "higher",
        ),
        "included_patient_required_criterion_provenance_coverage": (
            "Included patient criteria with valid resource provenance / required criteria.",
            "higher",
        ),
        "applicable_lifecycle_audit_completeness": (
            "Applicable runs with complete required lifecycle audit / applicable runs.",
            "higher",
        ),
        "orphan_mcp_request_rate": ("Orphan MCP requests / MCP requests.", "lower"),
        "duplicate_business_record_rate": ("Runs with duplicate business records / runs.", "lower"),
        "policy_denial_retry_rate": ("Policy denials retried / policy denials.", "lower"),
        "cancellation_finalization_rate": ("Cancelled runs finalized / cancelled runs.", "lower"),
        "authorization_bypass_rate": (
            "Successful authorization bypasses / authorization probes.",
            "lower",
        ),
        "self_approval_success_rate": (
            "Successful self-approvals / self-approval attempts.",
            "lower",
        ),
        "telemetry_redaction_violation_rate": (
            "Redaction violations / inspected telemetry records.",
            "lower",
        ),
        "overall_evidence_provenance_coverage": (
            "Evidence items with provenance / evidence items.",
            "higher",
        ),
        "median_latency_ms": ("Median end-to-end latency in milliseconds.", "lower"),
        "p95_latency_ms": ("P95 end-to-end latency in milliseconds.", "lower"),
        "fallback_rate": ("Runs using a fallback / runs.", "lower"),
        "structured_output_validity": ("Structurally valid outputs / outputs.", "higher"),
    }
    results = [
        _metric(
            name,
            candidate_metrics.get(name),
            definition,
            direction,
            baseline_metrics.get(name),
            int(candidate_data.get("sample_size", 0)),
            candidate_data.get("denominator"),
            name not in not_applicable,
        )
        for name, (definition, direction) in definitions.items()
    ]
    frameworks = candidate_data.get("frameworks", {})
    return results, frameworks if isinstance(frameworks, dict) else {}


def evaluate_candidate(
    candidate: ReleaseCandidate,
    candidate_data: Mapping[str, Any],
    baseline_data: Mapping[str, Any] | None,
    *,
    baseline_reference: dict[str, Any],
    scenario_definition_hash: str | None = None,
) -> ReleaseEvaluationReport:
    metrics, frameworks = normalize_metrics(candidate_data, baseline_data)
    gates = evaluate_gates(metrics)
    regressions = detect_regressions(metrics)
    decision, reasons = decide_release(gates, regressions)
    return ReleaseEvaluationReport(
        evaluation_id=str(uuid4()),
        report_version="phase6b-release-v1",
        candidate=candidate,
        baseline_reference=baseline_reference,
        evaluation_input_hash=stable_hash(
            {
                "candidate": candidate.model_dump(mode="json"),
                "candidate_data": candidate_data,
                "baseline": baseline_data,
                "scenario_definition_hash": scenario_definition_hash,
            }
        ),
        scenario_definition_hash=scenario_definition_hash,
        metrics=metrics,
        gates=gates,
        regressions=regressions,
        decision=decision,
        blocking_reasons=reasons,
        framework_results=frameworks,
        artifact_versions={"evaluation_suite": candidate.evaluation_suite_version},
        limitations=[
            "Synthetic Synthea development data only.",
            "Not clinically validated.",
            "No overall evidence-coverage gate is applied; missing evidence remains visible.",
        ]
        + candidate.limitations,
    )


def save_report(report: ReleaseEvaluationReport) -> tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / f"{report.evaluation_id}.json"
    md_path = REPORT_DIR / f"{report.evaluation_id}.md"
    json_path.write_text(report.model_dump_json(indent=2) + "\n")
    lines = [
        f"# Release evaluation {report.evaluation_id}",
        "",
        "Synthetic development evaluation; not clinically validated or production performance.",
        "",
        f"- Decision: **{report.decision}**",
        f"- Candidate: `{report.candidate.candidate_id}@{report.candidate.candidate_version}`",
        f"- Baseline: `{report.candidate.baseline_id or 'none'}`",
        "",
        "## Gates",
        "",
        "| Gate | Value | Threshold | Status |",
        "|---|---:|---:|---|",
    ]
    for gate in report.gates:
        value = gate.value if gate.value is not None else "N/A"
        status = "PASS" if gate.passed else gate.status.upper()
        lines.append(f"| {gate.name} | {value} | {gate.threshold} | {status} |")
    lines.extend(
        ["", "## Metrics", "", "| Metric | Candidate | Baseline | Delta |", "|---|---:|---:|---:|"]
    )
    for item in report.metrics:
        value = item.value if item.value is not None else "N/A"
        baseline = item.baseline_value if item.baseline_value is not None else "N/A"
        delta = item.delta if item.delta is not None else "N/A"
        lines.append(f"| {item.name} | {value} | {baseline} | {delta} |")
    if report.blocking_reasons:
        lines.extend(
            ["", "## Blocking reasons", "", *[f"- {reason}" for reason in report.blocking_reasons]]
        )
    lines.extend(
        [
            "",
            "## Framework results",
            "",
            "```json",
            json.dumps(report.framework_results, sort_keys=True, indent=2),
            "```",
        ]
    )
    lines.extend(["", "## Limitations", "", *[f"- {item}" for item in report.limitations]])
    md_path.write_text("\n".join(lines) + "\n")
    return json_path, md_path
