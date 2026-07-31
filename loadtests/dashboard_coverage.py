"""Validate provisioned Grafana PromQL against real local Prometheus data."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DASHBOARDS = ROOT / "infra/observability/grafana/dashboards"
METRIC_PATTERN = re.compile(r"\b(oncoagent_[a-zA-Z0-9_:]+)")
PROHIBITED_LABELS = {
    "run_id",
    "workflow_id",
    "review_id",
    "patient_id",
    "dataset_id",
    "user_id",
    "trace_id",
    "prompt",
    "url",
}
IDENTIFIER_VALUE = re.compile(
    r"(?:[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})",
    re.IGNORECASE,
)

NONZERO_TITLES = {
    "API request rate",
    "HTTP request pressure",
    "HTTP p95 latency",
    "Workflow outcomes",
    "Node duration",
    "Checkpoint resumes",
    "CrewAI outcomes",
    "Crew outcomes",
    "Task duration",
    "MCP request volume",
    "MCP latency",
    "MCP calls by tool",
    "Dataset denials",
    "Unsafe requests prevented",
    "Validation failures",
    "Self-approval denials",
    "Authorization denials",
    "Retry count",
    "Activity retries",
    "Recovery duration",
    "Worker recovery duration",
    "Cancellation latency",
    "Cancellation completion latency",
    "Overload rejections",
    "Development SLO success ratio",
    "Crew process interruptions",
    "Process interruptions",
    "Database duration",
}
LEGITIMATE_ZERO_TITLES = {
    "API error rate",
    "Awaiting workflow approvals",
    "Awaiting CrewAI reviews",
    "Orphan MCP requests",
    "Audit integrity failures",
    "Privacy violations",
    "Tool authorization denials",
    "Performance queue depth",
    "Workflow concurrency",
}


def _scenario(expression: str, title: str) -> str:
    if "mcp_" in expression:
        return "mcp"
    if "crew_" in expression:
        return "crewai"
    if "temporal_" in expression or "recovery" in title.lower():
        return "retry_or_recovery"
    if "cancellation" in expression.lower() or "cancellation" in title.lower():
        return "cancel"
    if "overload" in expression:
        return "overload"
    if "security_" in expression or "unsafe_" in expression or "validation_" in expression:
        return "governance"
    if "workflow_" in expression:
        return "langgraph"
    if "http_" in expression or "database_" in expression:
        return "api_load"
    return "platform_population"


def _read_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=20) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise TypeError("Prometheus returned a malformed response")
    return value


def _query(prometheus: str, expression: str, timestamp: float) -> dict[str, Any]:
    query = urllib.parse.urlencode({"query": expression, "time": f"{timestamp:.3f}"})
    return _read_json(f"{prometheus.rstrip('/')}/api/v1/query?{query}")


def _expressions(panel: dict[str, Any]) -> list[str]:
    return [
        target["expr"]
        for target in panel.get("targets", [])
        if isinstance(target, dict) and isinstance(target.get("expr"), str)
    ]


def validate(
    output: Path,
    start_epoch: float,
    end_epoch: float,
    prometheus: str = "http://127.0.0.1:9090",
    strict: bool = True,
) -> tuple[dict[str, Any], bool]:
    duration = max(60, int(end_epoch - start_epoch))
    timestamp = end_epoch
    metric_names = set(
        _read_json(f"{prometheus.rstrip('/')}/api/v1/label/__name__/values").get("data", [])
    )
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    referenced_metrics: set[str] = set()
    for path in sorted(DASHBOARDS.glob("*.json")):
        dashboard = json.loads(path.read_text(encoding="utf-8"))
        for panel in dashboard.get("panels", []):
            for expression in _expressions(panel):
                rendered = expression.replace("$__range", f"{duration}s")
                metrics = sorted(METRIC_PATTERN.findall(rendered))
                referenced_metrics.update(metrics)
                missing_metrics = [
                    metric
                    for metric in metrics
                    if metric not in metric_names
                    and re.sub(r"_(bucket|count|sum)$", "", metric) not in metric_names
                ]
                response = _query(prometheus, rendered, timestamp)
                data = response.get("data", {})
                result = data.get("result", []) if isinstance(data, dict) else []
                values: list[float] = []
                services: set[str] = set()
                for item in result if isinstance(result, list) else []:
                    metric = item.get("metric", {}) if isinstance(item, dict) else {}
                    services.add(str(metric.get("job") or metric.get("service") or ""))
                    sample = item.get("value", [None, None]) if isinstance(item, dict) else [None, None]
                    try:
                        values.append(float(sample[1]))
                    except (TypeError, ValueError, IndexError):
                        continue
                current_value = sum(values) if values else None
                title = str(panel.get("title", "Untitled"))
                nonzero_required = title in NONZERO_TITLES
                zero_legitimate = title in LEGITIMATE_ZERO_TITLES
                if missing_metrics:
                    failures.append(f"{dashboard.get('title')} / {title}: nonexistent metric")
                if strict and not result:
                    failures.append(f"{dashboard.get('title')} / {title}: no series")
                if strict and nonzero_required and not (current_value is not None and current_value > 0):
                    failures.append(f"{dashboard.get('title')} / {title}: nonzero evidence required")
                rows.append(
                    {
                        "dashboard": dashboard.get("title"),
                        "dashboard_uid": dashboard.get("uid"),
                        "panel_title": title,
                        "promql": rendered,
                        "expected_metric": metrics,
                        "scenario": _scenario(rendered, title),
                        "zero_legitimate": zero_legitimate,
                        "nonzero_required": nonzero_required,
                        "result_type": data.get("resultType") if isinstance(data, dict) else None,
                        "returned_series_count": len(result) if isinstance(result, list) else 0,
                        "current_value": current_value,
                        "timestamp": datetime.fromtimestamp(timestamp, UTC).isoformat(),
                        "service_or_job": sorted(item for item in services if item),
                        "correlation_window": {
                            "start": datetime.fromtimestamp(start_epoch, UTC).isoformat(),
                            "end": datetime.fromtimestamp(end_epoch, UTC).isoformat(),
                        },
                    }
                )
    series_query = urllib.parse.urlencode(
        {
            "match[]": '{__name__=~"oncoagent_.+"}',
            "start": f"{start_epoch:.3f}",
            "end": f"{end_epoch:.3f}",
        }
    )
    series = _read_json(f"{prometheus.rstrip('/')}/api/v1/series?{series_query}").get("data", [])
    high_cardinality = sorted(
        {
            label
            for item in series if isinstance(item, dict)
            for label in item
            if label in PROHIBITED_LABELS
        }
    )
    identifier_values = sorted(
        {
            label
            for item in series if isinstance(item, dict)
            for label, value in item.items()
            if label != "__name__" and isinstance(value, str) and IDENTIFIER_VALUE.search(value)
        }
    )
    if high_cardinality:
        failures.append("high-cardinality metric labels detected")
    if identifier_values:
        failures.append("identifier-bearing metric label values detected")
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "strict": strict,
        "panel_count": len(rows),
        "referenced_metric_count": len(referenced_metrics),
        "panels": rows,
        "high_cardinality_labels": high_cardinality,
        "identifier_bearing_labels": identifier_values,
        "failures": failures,
        "passed": not failures,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result, not failures


def calculate_slo(
    output: Path,
    start_epoch: float,
    end_epoch: float,
    prometheus: str = "http://127.0.0.1:9090",
) -> tuple[dict[str, Any], bool]:
    window = f"{max(60, int(end_epoch - start_epoch))}s"
    queries = {
        "requests": f"sum(increase(oncoagent_http_requests_total[{window}]))",
        "successful_requests": (
            f'sum(increase(oncoagent_http_requests_total{{status_class=~"2xx|3xx"}}[{window}]))'
        ),
        "p95_latency_seconds": (
            "histogram_quantile(0.95, sum by (le) "
            f"(increase(oncoagent_http_request_duration_seconds_bucket[{window}])))"
        ),
        "workflow_total": f"sum(increase(oncoagent_workflow_runs_total[{window}]))",
        "workflow_completed": (
            f'sum(increase(oncoagent_workflow_runs_total{{status="completed"}}[{window}]))'
        ),
        "mcp_total": f"sum(increase(oncoagent_mcp_requests_total[{window}]))",
        "mcp_success": (
            f'sum(increase(oncoagent_mcp_requests_total{{status="success"}}[{window}]))'
        ),
    }
    values: dict[str, float | None] = {}
    for name, expression in queries.items():
        response = _query(prometheus, expression, end_epoch)
        rows = response.get("data", {}).get("result", [])
        try:
            values[name] = float(rows[0]["value"][1]) if rows else None
        except (KeyError, TypeError, ValueError, IndexError):
            values[name] = None
    required = ("requests", "successful_requests", "p95_latency_seconds", "mcp_total", "mcp_success")
    telemetry_available = all(values[item] is not None for item in required)
    request_ratio = (
        values["successful_requests"] / values["requests"]
        if values["successful_requests"] is not None and values["requests"]
        else None
    )
    workflow_ratio = (
        values["workflow_completed"] / values["workflow_total"]
        if values["workflow_completed"] is not None and values["workflow_total"]
        else None
    )
    mcp_ratio = (
        values["mcp_success"] / values["mcp_total"]
        if values["mcp_success"] is not None and values["mcp_total"]
        else None
    )
    error_budget_consumption = (
        max(0.0, 1.0 - request_ratio) / 0.01 if request_ratio is not None else None
    )
    passed = bool(
        telemetry_available
        and request_ratio is not None
        and request_ratio >= 0.99
        and values["p95_latency_seconds"] is not None
        and values["p95_latency_seconds"] <= 10
        and mcp_ratio is not None
        and mcp_ratio >= 0.85
    )
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "window_seconds": max(60, int(end_epoch - start_epoch)),
        "telemetry_available": telemetry_available,
        "availability": request_ratio,
        "successful_request_ratio": request_ratio,
        "p95_latency_seconds": values["p95_latency_seconds"],
        "workflow_completion_ratio": workflow_ratio,
        "mcp_success_ratio": mcp_ratio,
        "error_budget_consumption": error_budget_consumption,
        "passed": passed,
        "queries": queries,
        "limitations": [
            "Local synthetic development SLO only; unavailable telemetry is never interpreted as passing."
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result, passed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--end", type=float, default=time.time())
    parser.add_argument("--prometheus", default="http://127.0.0.1:9090")
    parser.add_argument("--no-strict", action="store_true")
    parser.add_argument("--slo", action="store_true")
    args = parser.parse_args()
    if args.slo:
        _, passed = calculate_slo(args.output, args.start, args.end, args.prometheus)
    else:
        _, passed = validate(
            args.output,
            args.start,
            args.end,
            args.prometheus,
            strict=not args.no_strict,
        )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
