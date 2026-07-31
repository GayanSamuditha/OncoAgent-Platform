from __future__ import annotations

import json
from pathlib import Path

from dashboard_coverage import DASHBOARDS, PROHIBITED_LABELS, calculate_slo
from run import CONFIG_PATH, LoadSuite, SuiteFailure


def test_default_profiles_remain_within_hard_limits(monkeypatch) -> None:
    monkeypatch.delenv("ALLOW_HIGH_LOAD", raising=False)
    suite = LoadSuite()
    suite._validate_limits()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert config["profiles"]["burst"]["maximum_rps"] == 100
    assert config["profiles"]["mcp"]["maximum_rps"] == 30
    assert config["limits"]["normal"]["workflow_total"] == 50
    assert config["limits"]["high"]["workflow_total"] == 100


def test_nonlocal_target_is_rejected(monkeypatch) -> None:
    suite = LoadSuite()
    suite.config["api_base_url"] = "https://example.invalid"
    try:
        suite._validate_urls()
    except SuiteFailure as exc:
        assert "local allowlist" in str(exc)
    else:
        raise AssertionError("external load target was accepted")


def test_correlations_are_unique_bounded_and_prefixed() -> None:
    suite = LoadSuite()
    values = {suite._correlation(f"langgraph-{index}") for index in range(20)}
    assert len(values) == 20
    assert all(value.startswith("loadtest-") for value in values)
    assert all(len(value) <= 36 for value in values)


def test_every_dashboard_has_queryable_panels() -> None:
    dashboards = list(Path(DASHBOARDS).glob("*.json"))
    assert dashboards
    for path in dashboards:
        dashboard = json.loads(path.read_text(encoding="utf-8"))
        assert dashboard.get("uid")
        assert dashboard.get("panels")
        for panel in dashboard["panels"]:
            assert any(target.get("expr") for target in panel.get("targets", []))


def test_high_cardinality_label_registry_covers_sensitive_identifiers() -> None:
    assert {
        "run_id",
        "workflow_id",
        "review_id",
        "patient_id",
        "dataset_id",
        "user_id",
        "trace_id",
        "prompt",
        "url",
    } <= PROHIBITED_LABELS


def test_slo_accepts_latency_at_exact_boundary(monkeypatch, tmp_path) -> None:
    values = iter((100.0, 99.0, 10.0, 2.0, 2.0, 100.0, 99.0))

    def fake_query(*_args, **_kwargs):
        value = next(values)
        return {"data": {"result": [{"value": [0, str(value)]}]}}

    monkeypatch.setattr("dashboard_coverage._query", fake_query)
    result, passed = calculate_slo(tmp_path / "slo.json", 0, 60)
    assert passed
    assert result["p95_latency_seconds"] == 10.0


def test_latest_report_reuses_completed_output(monkeypatch, tmp_path, capsys) -> None:
    suite = LoadSuite()
    suite.config["output_directory"] = "."
    incomplete = tmp_path / "loadtest-newer"
    complete = tmp_path / "loadtest-complete"
    incomplete.mkdir(parents=True)
    complete.mkdir(parents=True)
    (incomplete / "summary.json").write_text(
        json.dumps({"test_id": "loadtest-newer", "end_time": None, "test_profiles": []})
    )
    (complete / "summary.json").write_text(
        json.dumps(
            {
                "test_id": "loadtest-complete",
                "end_time": "2026-07-30T00:00:00+00:00",
                "test_profiles": ["smoke"],
            }
        )
    )
    monkeypatch.setattr("run.ROOT", tmp_path)
    assert suite.latest_report() == 0
    assert "loadtest-complete" in capsys.readouterr().out


def test_post_load_recovery_wait_is_bounded_and_requires_stability(monkeypatch) -> None:
    suite = LoadSuite()
    outcomes = iter(
        (
            SuiteFailure("temporarily unavailable"),
            {"api": "healthy"},
            {"api": "healthy"},
        )
    )

    def health_snapshot():
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(suite, "_health_snapshot", health_snapshot)
    monkeypatch.setattr("run.time.sleep", lambda _seconds: None)
    suite._wait_for_post_load_recovery()
