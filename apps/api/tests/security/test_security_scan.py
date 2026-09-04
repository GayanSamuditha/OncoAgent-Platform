from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from scripts import security_scan  # noqa: E402


def completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, "")


@pytest.mark.parametrize(
    ("parser", "payload", "expected"),
    [
        ("pip-audit", "[]", 0),
        ("pip-audit", '[{"vulns":[{"id":"CVE-test"}]}]', 1),
        ("bandit", '{"results":[{"issue_text":"test"}]}', 1),
        ("trivy", '{"Results":[{"Vulnerabilities":[{"VulnerabilityID":"CVE-test"}]}]}', 1),
        ("npm", '{"metadata":{"vulnerabilities":{"high":2,"low":1}}}', 3),
    ],
)
def test_parse_findings(parser: str, payload: str, expected: int) -> None:
    assert security_scan._parse_findings(payload, parser) == expected


def test_command_observation_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security_scan.shutil, "which", lambda _: "/usr/bin/tool")
    calls = iter([completed("tool 1.2.3\n"), completed("[]")])
    monkeypatch.setattr(security_scan.subprocess, "run", lambda *args, **kwargs: next(calls))
    result = security_scan.command_observation(
        [sys.executable, "-m", "pip_audit"], "python", "pip-audit"
    )
    assert result["status"] == "passed"
    assert result["finding_count"] == 0
    assert result["tool_version"] == "tool 1.2.3"


def test_command_observation_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security_scan.shutil, "which", lambda _: "/usr/bin/tool")
    calls = iter([completed("tool 1.2.3\n"), completed('[{"vulns":[{"id":"CVE-test"}]}]', 1)])
    monkeypatch.setattr(security_scan.subprocess, "run", lambda *args, **kwargs: next(calls))
    result = security_scan.command_observation(
        [sys.executable, "-m", "pip_audit"], "python", "pip-audit"
    )
    assert result["status"] == "failed"
    assert result["finding_count"] == 1


def test_command_observation_missing_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security_scan.shutil, "which", lambda _: None)
    result = security_scan.command_observation(["trivy", "fs"], "container", "trivy")
    assert result["status"] == "not_evaluable"


def test_command_observation_malformed_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security_scan.shutil, "which", lambda _: "/usr/bin/tool")
    calls = iter([completed("tool 1.2.3\n"), completed("not-json")])
    monkeypatch.setattr(security_scan.subprocess, "run", lambda *args, **kwargs: next(calls))
    result = security_scan.command_observation(
        [sys.executable, "-m", "pip_audit"], "python", "pip-audit"
    )
    assert result["status"] == "error"


def test_command_observation_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security_scan.shutil, "which", lambda _: "/usr/bin/tool")

    def timeout(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired("tool", 1)

    monkeypatch.setattr(security_scan.subprocess, "run", timeout)
    result = security_scan.command_observation(
        [sys.executable, "-m", "pip_audit"], "python", "pip-audit"
    )
    assert result["status"] == "error"


def test_command_observation_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security_scan.shutil, "which", lambda _: "/usr/bin/tool")

    def transport_failure(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("transport unavailable")

    monkeypatch.setattr(security_scan.subprocess, "run", transport_failure)
    result = security_scan.command_observation(
        [sys.executable, "-m", "pip_audit"], "python", "pip-audit"
    )
    assert result["status"] == "not_evaluable"


def test_command_observation_unexpected_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security_scan.shutil, "which", lambda _: "/usr/bin/tool")
    calls = iter([completed("tool 1.2.3\n"), completed("[]", 2)])
    monkeypatch.setattr(security_scan.subprocess, "run", lambda *args, **kwargs: next(calls))
    result = security_scan.command_observation(
        [sys.executable, "-m", "pip_audit"], "python", "pip-audit"
    )
    assert result["status"] == "error"
