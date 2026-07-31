import json
import re
from pathlib import Path

from app.observability import metrics

DASHBOARD_DIR = (
    Path(__file__).resolve().parents[3] / "infra" / "observability" / "grafana" / "dashboards"
)
METRIC_REFERENCE = re.compile(r"\b(oncoagent_[a-zA-Z0-9_:]+)")


def _expressions(value):
    if isinstance(value, dict):
        if isinstance(value.get("expr"), str):
            yield value["expr"]
        for child in value.values():
            yield from _expressions(child)
    elif isinstance(value, list):
        for child in value:
            yield from _expressions(child)


def test_dashboard_promql_references_declared_metrics() -> None:
    source = Path(metrics.__file__).read_text()
    declared = set(re.findall(r'"(oncoagent_[a-z0-9_]+)"', source))
    for dashboard_path in DASHBOARD_DIR.glob("*.json"):
        dashboard = json.loads(dashboard_path.read_text())
        for expression in _expressions(dashboard):
            for reference in METRIC_REFERENCE.findall(expression):
                base = re.sub(r"_(bucket|count|sum)$", "", reference)
                assert reference in declared or base in declared, (
                    f"{dashboard_path.name} references undeclared metric {reference}"
                )


def test_crewai_dashboard_uses_current_bounded_labels_and_selected_range() -> None:
    dashboard = json.loads((DASHBOARD_DIR / "oncoagent-crewai.json").read_text())
    expressions = "\n".join(_expressions(dashboard))
    assert "outcome" in expressions
    assert "task_name" in expressions
    assert "oncoagent-temporal-worker" in expressions
    assert "$__range" in expressions
    assert "sum by (status) (rate(oncoagent_crew_runs_total" not in expressions
